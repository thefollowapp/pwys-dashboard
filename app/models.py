from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
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
    # "registration" | "weekly_practice" | "game_day" | "cancellation"; null for inbound replies and anything untagged.
    message_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
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
