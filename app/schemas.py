from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SmsEventIn(BaseModel):
    contact_phone: str = Field(min_length=1)
    direction: str = Field(pattern="^(outbound|inbound)$")
    status: str = Field(pattern="^(sent|delivered|failed|received)$")
    monday_item_id: str | None = None
    location: str | None = None
    program_tier: str | None = None
    message_type: Literal["registration", "weekly_practice", "game_day"] | None = None
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
