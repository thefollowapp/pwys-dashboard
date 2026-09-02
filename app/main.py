import os

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.actions import CancellationNoticeError, send_cancellation_notice
from app.auth import NotAuthenticated, get_current_user, hash_password, login_user, logout_user, require_user, verify_password
from app.database import Base, engine, get_db, run_column_migrations
from app.ingest import router as ingest_router
from app.metrics import get_locations, get_recent_activity, get_summary, get_timeseries
from app.models import User

Base.metadata.create_all(bind=engine)
run_column_migrations()

app = FastAPI(title="PWYS Communications Dashboard")

session_secret = os.getenv("SESSION_SECRET")
if not session_secret:
    raise RuntimeError("SESSION_SECRET must be set (see .env.example)")
app.add_middleware(SessionMiddleware, secret_key=session_secret, same_site="lax", https_only=os.getenv("ENV") == "production")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(ingest_router)


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return RedirectResponse(url="/dashboard" if user else "/login")


@app.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_user(request, db):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Invalid email or password."}, status_code=401
        )
    login_user(request, user)
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/dashboard")
def dashboard(
    request: Request,
    days: int = 30,
    location: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    period = None if days == 0 else days
    summary = get_summary(db, days=period, location=location)
    timeseries = get_timeseries(db, days=period or 3650, location=location)
    locations = get_locations(db)
    activity = get_recent_activity(db)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "summary": summary,
            "timeseries": timeseries,
            "locations": locations,
            "selected_location": location or "",
            "selected_days": days,
            "activity": activity,
        },
    )


@app.get("/cancellations/new")
def cancellation_notice_form(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "cancellation_new.html",
        {"user": user, "locations": get_locations(db), "error": None},
    )


@app.post("/cancellations/new")
def cancellation_notice_submit(
    request: Request,
    location: str = Form(...),
    message: str = Form(...),
    confirm: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not confirm:
        return templates.TemplateResponse(
            request,
            "cancellation_new.html",
            {
                "user": user,
                "locations": get_locations(db),
                "error": "Please check the confirmation box to send.",
                "location": location,
                "message": message,
            },
            status_code=400,
        )

    try:
        send_cancellation_notice(location=location, message=message, triggered_by=user.email)
    except CancellationNoticeError as exc:
        return templates.TemplateResponse(
            request,
            "cancellation_new.html",
            {
                "user": user,
                "locations": get_locations(db),
                "error": str(exc),
                "location": location,
                "message": message,
            },
            status_code=502,
        )

    return templates.TemplateResponse(
        request,
        "cancellation_new.html",
        {
            "user": user,
            "locations": get_locations(db),
            "error": None,
            "success": f"Cancellation notice for {location} was sent to Make.com for delivery.",
        },
    )


@app.get("/account")
def account_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(request, "account.html", {"user": user, "error": None, "success": None})


@app.post("/account/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not verify_password(current_password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "error": "Current password is incorrect.", "success": None},
            status_code=401,
        )
    if len(new_password) < 10:
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "error": "New password must be at least 10 characters.", "success": None},
            status_code=400,
        )
    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "account.html",
            {"user": user, "error": "New passwords don't match.", "success": None},
            status_code=400,
        )

    user.password_hash = hash_password(new_password)
    db.add(user)
    db.commit()
    return templates.TemplateResponse(
        request, "account.html", {"user": user, "error": None, "success": "Password updated."}
    )
