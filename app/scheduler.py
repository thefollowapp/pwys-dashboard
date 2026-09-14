"""Fires recurring notices (e.g. a weekly Game Day-style reminder) on their own schedule.

Runs in-process on a one-minute tick and reuses the same Cancellation notice webhook a
staff member's "Send now" click goes through — the schedule is the only thing this adds.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler

from app.actions import NoticeError, send_targeted_notice
from app.database import SessionLocal
from app.metrics import get_locations
from app.models import RecurringNotice

logger = logging.getLogger("app.scheduler")

_scheduler: BackgroundScheduler | None = None


def _already_sent_today(last_sent_at: datetime | None, now_local: datetime) -> bool:
    if last_sent_at is None:
        return False
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
    return last_sent_at.astimezone(now_local.tzinfo).date() == now_local.date()


def check_and_send_due_notices() -> None:
    db = SessionLocal()
    try:
        notices = db.query(RecurringNotice).filter(RecurringNotice.active.is_(True)).all()
        for notice in notices:
            try:
                tz = ZoneInfo(notice.timezone)
            except ZoneInfoNotFoundError:
                logger.warning("Recurring notice %s has an unknown timezone %r, skipping", notice.id, notice.timezone)
                continue

            now_local = datetime.now(tz)
            if now_local.weekday() != notice.day_of_week or now_local.strftime("%H:%M") != notice.time_of_day:
                continue
            if _already_sent_today(notice.last_sent_at, now_local):
                continue

            locations = notice.locations or get_locations(db)
            try:
                send_targeted_notice(
                    locations=locations,
                    message=notice.message,
                    triggered_by=f"recurring:{notice.name}",
                    message_type=notice.message_type,
                )
            except NoticeError:
                logger.exception("Recurring notice %s (%s) failed to send", notice.id, notice.name)
                continue

            notice.last_sent_at = datetime.now(timezone.utc)
            db.add(notice)
            db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(check_and_send_due_notices, "interval", minutes=1, id="recurring_notices")
    _scheduler.start()
