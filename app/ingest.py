import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmailEvent, SmsEvent
from app.schemas import EmailEventIn, SmsEventIn

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def verify_ingest_key(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("INGEST_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="INGEST_API_KEY is not configured on the server")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")


@router.post("/sms", status_code=201, dependencies=[Depends(verify_ingest_key)])
def ingest_sms(event: SmsEventIn, db: Session = Depends(get_db)):
    row = SmsEvent(
        monday_item_id=event.monday_item_id,
        contact_phone=event.contact_phone,
        location=event.location,
        program_tier=event.program_tier,
        direction=event.direction,
        status=event.status,
        body=event.body,
        twilio_sid=event.twilio_sid,
        **({"created_at": event.occurred_at} if event.occurred_at else {}),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Make.com retries webhooks on transient failures; a repeat twilio_sid means
        # this send was already logged, so treat it as a success rather than erroring.
        db.rollback()
        existing = db.query(SmsEvent).filter(SmsEvent.twilio_sid == event.twilio_sid).first()
        return {"id": existing.id if existing else None, "duplicate": True}
    return {"id": row.id}


@router.post("/email", status_code=201, dependencies=[Depends(verify_ingest_key)])
def ingest_email(event: EmailEventIn, db: Session = Depends(get_db)):
    row = EmailEvent(
        robly_contact_id=event.robly_contact_id,
        email=event.email,
        location=event.location,
        program_tier=event.program_tier,
        event_type=event.event_type,
        subject=event.subject,
        **({"created_at": event.occurred_at} if event.occurred_at else {}),
    )
    db.add(row)
    db.commit()
    return {"id": row.id}
