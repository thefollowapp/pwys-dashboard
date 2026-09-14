import os
import re

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.actions import NoticeError, send_cancellation_notice, send_move_indoors_notice, send_targeted_notice
from app.auth import (
    NotAdmin,
    NotAuthenticated,
    get_current_user,
    hash_password,
    login_user,
    logout_user,
    require_admin,
    require_user,
    verify_password,
)
from app.database import Base, SessionLocal, engine, get_db, run_column_migrations
from app.ingest import router as ingest_router
from app.metrics import get_locations, get_recent_activity, get_summary, get_timeseries
from app.models import NoticeType, RecurringNotice, User
from app.scheduler import start_scheduler

Base.metadata.create_all(bind=engine)
run_column_migrations()


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return slug or "notice"


def _unique_slug(db: Session, column, label: str) -> str:
    base = _slugify(label)
    slug = base
    suffix = 2
    while db.query(column).filter(column == slug).first():
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


def _seed_default_notice_types() -> None:
    """One-time bootstrap: "Soccer is on" was a hardcoded notice type before admins
    could define their own; give it a real row so it behaves like any other."""
    db = SessionLocal()
    try:
        if db.query(NoticeType).filter(NoticeType.key == "practice_on").first():
            return
        db.add(
            NoticeType(
                key="practice_on",
                label="Soccer is on",
                default_message=(
                    "Soccer is finally back! PWYS will be at Gaisman Park today, 5:30-6:30pm. / "
                    "El futbol ha vuelto! PWYS estara en Gaisman Park hoy, de 5:30 a 6:30pm."
                ),
                created_by="system",
            )
        )
        db.commit()
    finally:
        db.close()


_seed_default_notice_types()
start_scheduler()

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


@app.exception_handler(NotAdmin)
async def not_admin_handler(request: Request, exc: NotAdmin):
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        return templates.TemplateResponse(request, "forbidden.html", {"user": user}, status_code=403)
    finally:
        db.close()


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
def cancellation_notice_redirect():
    return RedirectResponse(url="/notices/new", status_code=308)


def _active_notice_types(db: Session) -> list[NoticeType]:
    return db.query(NoticeType).filter(NoticeType.active.is_(True)).order_by(NoticeType.label).all()


@app.get("/notices/new")
def notice_form(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request,
        "notice_new.html",
        {"user": user, "locations": get_locations(db), "notice_types": _active_notice_types(db), "error": None},
    )


@app.post("/notices/new")
def notice_submit(
    request: Request,
    notice_type: str = Form(...),
    message: str = Form(...),
    notify_locations: list[str] = Form([]),
    excluded_locations: list[str] = Form([]),
    confirm: str | None = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    all_locations = get_locations(db)
    notice_types = _active_notice_types(db)
    custom_type = next((nt for nt in notice_types if nt.key == notice_type), None)
    form_state = {
        "user": user,
        "locations": all_locations,
        "notice_types": notice_types,
        "notice_type": notice_type,
        "selected_locations": notify_locations,
        "excluded_locations": excluded_locations,
        "message": message,
    }

    if not confirm:
        return templates.TemplateResponse(
            request, "notice_new.html", {**form_state, "error": "Please check the confirmation box to send."}, status_code=400
        )
    if notice_type == "move_indoors":
        pass
    elif notice_type == "cancellation" or custom_type is not None:
        if not notify_locations:
            return templates.TemplateResponse(
                request, "notice_new.html", {**form_state, "error": "Please select at least one location."}, status_code=400
            )
    else:
        return templates.TemplateResponse(
            request, "notice_new.html", {**form_state, "error": "Unknown notice type."}, status_code=400
        )

    try:
        if notice_type == "move_indoors":
            send_move_indoors_notice(excluded_locations=excluded_locations, message=message, triggered_by=user.email)
            excluded_note = f" (excluding {', '.join(excluded_locations)})" if excluded_locations else ""
            success = f"Move indoors notice was sent to Make.com for delivery{excluded_note}."
        else:
            locations_note = "all locations" if set(notify_locations) == set(all_locations) else ", ".join(notify_locations)
            if notice_type == "cancellation":
                send_cancellation_notice(locations=notify_locations, message=message, triggered_by=user.email)
                success = f"Cancellation notice for {locations_note} was sent to Make.com for delivery."
            else:
                send_targeted_notice(
                    locations=notify_locations, message=message, triggered_by=user.email, message_type=custom_type.key
                )
                success = f"{custom_type.label} notice for {locations_note} was sent to Make.com for delivery."
    except NoticeError as exc:
        return templates.TemplateResponse(request, "notice_new.html", {**form_state, "error": str(exc)}, status_code=502)

    return templates.TemplateResponse(
        request,
        "notice_new.html",
        {"user": user, "locations": get_locations(db), "notice_types": notice_types, "error": None, "success": success},
    )


@app.get("/admin/notice-types")
def notice_types_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice_types = db.query(NoticeType).order_by(NoticeType.active.desc(), NoticeType.label).all()
    return templates.TemplateResponse(
        request, "admin_notice_types.html", {"user": user, "notice_types": notice_types, "error": None}
    )


@app.post("/admin/notice-types")
def notice_types_create(
    request: Request,
    label: str = Form(...),
    default_message: str = Form(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    label = label.strip()
    if not label or not default_message.strip():
        notice_types = db.query(NoticeType).order_by(NoticeType.active.desc(), NoticeType.label).all()
        return templates.TemplateResponse(
            request,
            "admin_notice_types.html",
            {"user": user, "notice_types": notice_types, "error": "Please fill in both the name and default message."},
            status_code=400,
        )
    key = _unique_slug(db, NoticeType.key, label)
    db.add(NoticeType(key=key, label=label, default_message=default_message.strip(), created_by=user.email))
    db.commit()
    return RedirectResponse(url="/admin/notice-types", status_code=303)


@app.post("/admin/notice-types/{notice_type_id}/toggle")
def notice_types_toggle(notice_type_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice_type = db.get(NoticeType, notice_type_id)
    if notice_type is not None:
        notice_type.active = not notice_type.active
        db.add(notice_type)
        db.commit()
    return RedirectResponse(url="/admin/notice-types", status_code=303)


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _schedule_summary(notice: RecurringNotice) -> str:
    day = _DAY_NAMES[notice.day_of_week] if 0 <= notice.day_of_week < 7 else "?"
    return f"Every {day} at {notice.time_of_day}"


@app.get("/admin/recurring-notices")
def recurring_notices_page(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    notices = db.query(RecurringNotice).order_by(RecurringNotice.name).all()
    return templates.TemplateResponse(
        request,
        "admin_recurring_notices.html",
        {
            "user": user,
            "notices": notices,
            "schedule_summary": _schedule_summary,
            "day_names": _DAY_NAMES,
            "locations": get_locations(db),
            "form_notice": None,
            "error": None,
        },
    )


@app.get("/admin/recurring-notices/new")
def recurring_notices_new(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "admin_recurring_notice_form.html",
        {"user": user, "notice": None, "locations": get_locations(db), "day_names": _DAY_NAMES, "error": None},
    )


def _parse_time_of_day(raw: str) -> str | None:
    if re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", raw or ""):
        hour, minute = raw.split(":")
        if int(hour) < 24:
            return raw
    return None


@app.post("/admin/recurring-notices/new")
def recurring_notices_create(
    request: Request,
    name: str = Form(...),
    message: str = Form(...),
    day_of_week: int = Form(...),
    time_of_day: str = Form(...),
    notify_locations: list[str] = Form([]),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    parsed_time = _parse_time_of_day(time_of_day)
    error = None
    if not name.strip() or not message.strip():
        error = "Please fill in both the name and message."
    elif not (0 <= day_of_week <= 6):
        error = "Please choose a valid day of the week."
    elif parsed_time is None:
        error = "Please choose a valid time."
    if error:
        return templates.TemplateResponse(
            request,
            "admin_recurring_notice_form.html",
            {"user": user, "notice": None, "locations": get_locations(db), "day_names": _DAY_NAMES, "error": error},
            status_code=400,
        )

    message_type = _unique_slug(db, RecurringNotice.message_type, name.strip())
    db.add(
        RecurringNotice(
            name=name.strip(),
            message_type=message_type,
            message=message.strip(),
            locations=notify_locations or None,
            day_of_week=day_of_week,
            time_of_day=parsed_time,
            created_by=user.email,
        )
    )
    db.commit()
    return RedirectResponse(url="/admin/recurring-notices", status_code=303)


@app.get("/admin/recurring-notices/{notice_id}/edit")
def recurring_notices_edit_form(
    notice_id: int, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    notice = db.get(RecurringNotice, notice_id)
    if notice is None:
        return RedirectResponse(url="/admin/recurring-notices", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin_recurring_notice_form.html",
        {"user": user, "notice": notice, "locations": get_locations(db), "day_names": _DAY_NAMES, "error": None},
    )


@app.post("/admin/recurring-notices/{notice_id}/edit")
def recurring_notices_edit(
    notice_id: int,
    request: Request,
    name: str = Form(...),
    message: str = Form(...),
    day_of_week: int = Form(...),
    time_of_day: str = Form(...),
    notify_locations: list[str] = Form([]),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    notice = db.get(RecurringNotice, notice_id)
    if notice is None:
        return RedirectResponse(url="/admin/recurring-notices", status_code=303)

    parsed_time = _parse_time_of_day(time_of_day)
    error = None
    if not name.strip() or not message.strip():
        error = "Please fill in both the name and message."
    elif not (0 <= day_of_week <= 6):
        error = "Please choose a valid day of the week."
    elif parsed_time is None:
        error = "Please choose a valid time."
    if error:
        return templates.TemplateResponse(
            request,
            "admin_recurring_notice_form.html",
            {"user": user, "notice": notice, "locations": get_locations(db), "day_names": _DAY_NAMES, "error": error},
            status_code=400,
        )

    notice.name = name.strip()
    notice.message = message.strip()
    notice.day_of_week = day_of_week
    notice.time_of_day = parsed_time
    notice.locations = notify_locations or None
    db.add(notice)
    db.commit()
    return RedirectResponse(url="/admin/recurring-notices", status_code=303)


@app.post("/admin/recurring-notices/{notice_id}/toggle")
def recurring_notices_toggle(notice_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice = db.get(RecurringNotice, notice_id)
    if notice is not None:
        notice.active = not notice.active
        db.add(notice)
        db.commit()
    return RedirectResponse(url="/admin/recurring-notices", status_code=303)


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
