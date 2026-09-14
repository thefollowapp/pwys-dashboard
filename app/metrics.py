from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmailEvent, NoticeType, RecurringNotice, SmsEvent

# Types the app itself sends and tags without an admin-managed row to name them.
SYSTEM_TYPE_LABELS = {
    "registration": "Registration",
    "weekly_practice": "Weekly practice",
    "game_day": "Game Day",
    "cancellation": "Cancellation",
    "move_indoors": "Move indoors",
}


def _since(days: int | None) -> datetime | None:
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def _type_labels(db: Session) -> dict[str, str]:
    """Maps every known message_type key to a display label: built-ins, then
    admin-defined notice types and recurring notices (active or not, so history
    involving a since-deactivated type still reads sensibly)."""
    labels = dict(SYSTEM_TYPE_LABELS)
    for key, label in db.execute(select(NoticeType.key, NoticeType.label)).all():
        labels[key] = label
    for message_type, name in db.execute(select(RecurringNotice.message_type, RecurringNotice.name)).all():
        labels[message_type] = name
    return labels


def get_summary(db: Session, days: int | None = 30, location: str | None = None) -> dict:
    since = _since(days)

    sms_filters = []
    email_filters = []
    if since is not None:
        sms_filters.append(SmsEvent.created_at >= since)
        email_filters.append(EmailEvent.created_at >= since)
    if location:
        sms_filters.append(SmsEvent.location == location)
        email_filters.append(EmailEvent.location == location)

    sms_sent = db.scalar(select(func.count()).where(SmsEvent.direction == "outbound", *sms_filters)) or 0
    sms_replies = db.scalar(select(func.count()).where(SmsEvent.direction == "inbound", *sms_filters)) or 0
    sms_unique_sent = db.scalar(
        select(func.count(func.distinct(SmsEvent.contact_phone))).where(SmsEvent.direction == "outbound", *sms_filters)
    ) or 0
    sms_unique_replied = db.scalar(
        select(func.count(func.distinct(SmsEvent.contact_phone))).where(SmsEvent.direction == "inbound", *sms_filters)
    ) or 0

    counts_by_type = dict(
        db.execute(
            select(SmsEvent.message_type, func.count())
            .where(SmsEvent.direction == "outbound", SmsEvent.message_type.is_not(None), *sms_filters)
            .group_by(SmsEvent.message_type)
        ).all()
    )
    labels = _type_labels(db)
    # Always show every known type (even at 0), plus anything with sends under a type
    # that's since been deleted, so a tile never silently vanishes mid-history.
    all_keys = set(labels) | set(counts_by_type)
    system_order = {key: i for i, key in enumerate(SYSTEM_TYPE_LABELS)}
    sms_by_type = sorted(
        (
            {"key": key, "label": labels.get(key, key), "count": counts_by_type.get(key, 0)}
            for key in all_keys
        ),
        key=lambda row: (system_order.get(row["key"], len(system_order)), row["label"]),
    )

    emails_sent = db.scalar(select(func.count()).where(EmailEvent.event_type == "sent", *email_filters)) or 0
    emails_opened = db.scalar(
        select(func.count(func.distinct(EmailEvent.email))).where(EmailEvent.event_type == "opened", *email_filters)
    ) or 0
    emails_clicked = db.scalar(
        select(func.count(func.distinct(EmailEvent.email))).where(EmailEvent.event_type == "clicked", *email_filters)
    ) or 0

    sms_reply_rate = round(100 * sms_unique_replied / sms_unique_sent, 1) if sms_unique_sent else None
    email_open_rate = round(100 * emails_opened / emails_sent, 1) if emails_sent else None
    email_click_rate = round(100 * emails_clicked / emails_sent, 1) if emails_sent else None

    return {
        "sms_sent": sms_sent,
        "sms_replies": sms_replies,
        "sms_reply_rate": sms_reply_rate,
        "sms_by_type": sms_by_type,
        "emails_sent": emails_sent,
        "emails_opened": emails_opened,
        "emails_clicked": emails_clicked,
        "email_open_rate": email_open_rate,
        "email_click_rate": email_click_rate,
    }


PRACTICE_LOCATIONS = [
    "Jackson Elementary",
    "Willow Oaks Elementary",
    "Parkway Village Elementary",
    "Treadwell Park",
    "Binghampton",
    "Gaisman Park",
    "Gaston Park",
    "Jennette Place",
]


def get_locations(db: Session) -> list[str]:
    sms_locations = db.scalars(
        select(SmsEvent.location).where(SmsEvent.location.is_not(None)).distinct()
    ).all()
    email_locations = db.scalars(
        select(EmailEvent.location).where(EmailEvent.location.is_not(None)).distinct()
    ).all()
    return sorted(set(PRACTICE_LOCATIONS) | set(sms_locations) | set(email_locations))


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

    labels = _type_labels(db)
    activity = [
        {
            "type": "SMS",
            "detail": (
                (labels.get(row.message_type, row.message_type) + " · " if row.message_type else "")
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
