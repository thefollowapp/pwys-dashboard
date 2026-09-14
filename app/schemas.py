from datetime import datetime

from pydantic import BaseModel, Field


class SmsEventIn(BaseModel):
    contact_phone: str = Field(min_length=1)
    direction: str = Field(pattern="^(outbound|inbound)$")
    status: str = Field(pattern="^(sent|delivered|failed|received)$")
    monday_item_id: str | None = None
    location: str | None = None
    program_tier: str | None = None
    # System type ("registration" | "weekly_practice" | "game_day" | "cancellation" | "move_indoors"), or an
    # admin-defined NoticeType.key / RecurringNotice.message_type — not a fixed enum since those are user-managed.
    message_type: str | None = Field(default=None, max_length=64)
    body: str | None = None
    twilio_sid: str | None = None
    occurred_at: datetime | None = None


class EmailEventIn(BaseModel):
    email: str = Field(min_length=1)
    event_type: str = Field(pattern="^(sent|opened|clicked|bounced|unsubscribed)$")
    robly_contact_id: str | None = None
    location: str | None = None
    program_tier: str | None = None
    subject: str | None = None
    occurred_at: datetime | None = None
