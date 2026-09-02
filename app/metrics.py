from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmailEvent, SmsEvent


def _since(days: int | None) -> datetime | None:
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def get_summary(db: Session, days: int | None = 30, location: str | None = None) -> dict:
    since = _since(days)

    sms_q = select(SmsEvent)
    email_q = select(EmailEvent)
    if since is not None:
        sms_q = sms_q.where(SmsEvent.created_at >= since)
        email_q = email_q.where(EmailEvent.created_at >= since)
    if location:
        sms_q = sms_q.where(SmsEvent.location == location)
        email_q = email_q.where(EmailEvent.location == location)

    sms_sent = db.scalar(
        select(func.count()).select_from(sms_q.where(SmsEvent.direction == "outbound").subquery())
    ) or 0
    sms_replies = db.scalar(
        select(func.count()).select_from(sms_q.where(SmsEvent.direction == "inbound").subquery())
    ) or 0
    sms_unique_sent = db.scalar(
        select(func.count(func.distinct(SmsEvent.contact_phone))).select_from(
            sms_q.where(SmsEvent.direction == "outbound").subquery()
        )
    ) or 0
    sms_unique_replied = db.scalar(
        select(func.count(func.distinct(SmsEvent.contact_phone))).select_from(
            sms_q.where(SmsEvent.direction == "inbound").subquery()
        )
    ) or 0

    def _sent_by_type(message_type: str) -> int:
        return db.scalar(
            select(func.count()).select_from(
                sms_q.where(SmsEvent.direction == "outbound", SmsEvent.message_type == message_type).subquery()
            )
        ) or 0

    registration_sent = _sent_by_type("registration")
    weekly_practice_sent = _sent_by_type("weekly_practice")
    game_day_sent = _sent_by_type("game_day")
    cancellation_sent = _sent_by_type("cancellation")

    emails_sent = db.scalar(
        select(func.count()).select_from(email_q.where(EmailEvent.event_type == "sent").subquery())
    ) or 0
    emails_opened = db.scalar(
        select(func.count(func.distinct(EmailEvent.email))).select_from(
            email_q.where(EmailEvent.event_type == "opened").subquery()
        )
    ) or 0
    emails_clicked = db.scalar(
        select(func.count(func.distinct(EmailEvent.email))).select_from(
            email_q.where(EmailEvent.event_type == "clicked").subquery()
        )
    ) or 0

    sms_reply_rate = round(100 * sms_unique_replied / sms_unique_sent, 1) if sms_unique_sent else None
    email_open_rate = round(100 * emails_opened / emails_sent, 1) if emails_sent else None
    email_click_rate = round(100 * emails_clicked / emails_sent, 1) if emails_sent else None

    return {
        "sms_sent": sms_sent,
        "sms_replies": sms_replies,
        "sms_reply_rate": sms_reply_rate,
        "registration_sent": registration_sent,
        "weekly_practice_sent": weekly_practice_sent,
        "game_day_sent": game_day_sent,
        "cancellation_sent": cancellation_sent,
        "emails_sent": emails_sent,
        "emails_opened": emails_opened,
        "emails_clicked": emails_clicked,
        "email_open_rate": email_open_rate,
        "email_click_rate": email_click_rate,
    }


def get_locations(db: Session) -> list[str]:
    sms_locations = db.scalars(
        select(SmsEvent.location).where(SmsEvent.location.is_not(None)).distinct()
    ).all()
    email_locations = db.scalars(
        select(EmailEvent.location).where(EmailEvent.location.is_not(None)).distinct()
    ).all()
    return sorted(set(sms_locations) | set(email_locations))


def get_timeseries(db: Session, days: int = 30, location: str | None = None) -> list[dict]:
    since = _since(days) or (datetime.now(timezone.utc) - timedelta(days=365 * 10))

    day_bucket_sms = func.date(SmsEvent.created_at)
    sms_q = (
        select(day_bucket_sms.label("day"), func.count().label("count"))
        .where(SmsEvent.created_at >= since, SmsEvent.direction == "outbound")
        .group_by("day")
    )
    day_bucket_email = func.date(EmailEvent.created_at)
    email_q = (
        select(day_bucket_email.label("day"), func.count().label("count"))
        .where(EmailEvent.created_at >= since, EmailEvent.event_type == "sent")
        .group_by("day")
    )
    if location:
        sms_q = sms_q.where(SmsEvent.location == location)
        email_q = email_q.where(EmailEvent.location == location)

    sms_by_day = {str(day): count for day, count in db.execute(sms_q).all()}
    email_by_day = {str(day): count for day, count in db.execute(email_q).all()}

    all_days = sorted(set(sms_by_day) | set(email_by_day))
    return [
        {"day": day, "sms_sent": sms_by_day.get(day, 0), "emails_sent": email_by_day.get(day, 0)}
        for day in all_days
    ]


def get_recent_activity(db: Session, limit: int = 25) -> list[dict]:
    sms_rows = db.scalars(select(SmsEvent).order_by(SmsEvent.created_at.desc()).limit(limit)).all()
    email_rows = db.scalars(select(EmailEvent).order_by(EmailEvent.created_at.desc()).limit(limit)).all()

    _type_labels = {
        "registration": "Registration",
        "weekly_practice": "Weekly practice",
        "game_day": "Game Day",
        "cancellation": "Cancellation",
    }
    activity = [
        {
            "type": "SMS",
            "detail": (
                (_type_labels.get(row.message_type, row.message_type) + " · " if row.message_type else "")
                + f"{row.direction} · {row.status}"
                + (f" · {row.location}" if row.location else "")
            ),
            "created_at": row.created_at,
        }
        for row in sms_rows
    ] + [
        {
            "type": "Email",
            "detail": f"{row.event_type}" + (f" · {row.location}" if row.location else ""),
            "created_at": row.created_at,
        }
        for row in email_rows
    ]
    activity.sort(key=lambda r: r["created_at"], reverse=True)
    return activity[:limit]
