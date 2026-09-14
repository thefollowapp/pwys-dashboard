from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SmsEvent(Base):
    """One row per outbound SMS send or inbound SMS reply, logged by Make.com."""

    __tablename__ = "sms_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monday_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    contact_phone: Mapped[str] = mapped_column(String(32), index=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    program_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "registration" | "weekly_practice" | "game_day" | "move_indoors" | a NoticeType.key | a
    # RecurringNotice.message_type; null for inbound replies and anything untagged.
    message_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(16))  # "outbound" | "inbound"
    status: Mapped[str] = mapped_column(String(32))  # "sent" | "delivered" | "failed" | "received"
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_sid: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EmailEvent(Base):
    """One row per Robly email send/open/click, logged by Make.com."""

    __tablename__ = "email_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    robly_contact_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    program_tier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(32))  # "sent" | "opened" | "clicked" | "bounced" | "unsubscribed"
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class NoticeType(Base):
    """A custom "send now" notice type staff can pick on the Send Notice page.

    Admin-managed so PWYS can add new ones (e.g. "World Cup") without a code change.
    Behaves like the built-in Cancellation notice: staff pick one or more locations and
    it texts everyone registered there. "Cancellation" and "Move Indoors" are separate,
    permanent built-ins handled in code and aren't rows in this table.
    """

    __tablename__ = "notice_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(128))
    default_message: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecurringNotice(Base):
    """A weekly notice the dashboard sends on its own schedule (e.g. Game Day reminders).

    Reuses the same Cancellation webhook/Twilio pipeline as a "send now" notice; the
    dashboard's own scheduler is just what decides when to fire it. Admin-managed.
    """

    __tablename__ = "recurring_notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    message_type: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    locations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # None/empty = every location
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0 = Monday ... 6 = Sunday
    time_of_day: Mapped[str] = mapped_column(String(5))  # "HH:MM", 24-hour
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    active: Mapped[bool] = mapped_column(default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
