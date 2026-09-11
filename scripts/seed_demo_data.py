"""Populate the local dev database with fake SMS/email events, purely for previewing the dashboard UI.

Do NOT run this against a production database.

Usage: python scripts/seed_demo_data.py
"""

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.models import EmailEvent, SmsEvent

LOCATIONS = ["Frayser Park", "Raleigh Park", "Whitehaven Park", "Hickory Hill Park", "Orange Mound Park"]
TIERS = ["Neighborhood", "Game Day", "World Cup"]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        for i in range(300):
            sent_at = now - timedelta(days=random.randint(0, 45), hours=random.randint(0, 23))
            phone = f"+1901555{1000 + (i % 80):04d}"
            location = random.choice(LOCATIONS)
            db.add(
                SmsEvent(
                    contact_phone=phone,
                    location=location,
                    program_tier=random.choice(TIERS),
                    message_type=random.choice(
                        ["registration", "weekly_practice", "game_day", "cancellation", "move_indoors", "practice_on"]
                    ),
                    direction="outbound",
                    status="delivered",
                    body="Practice reminder for this week.",
                    twilio_sid=f"SMdemo{i:06d}",
                    created_at=sent_at,
                )
            )
            if random.random() < 0.35:
                db.add(
                    SmsEvent(
                        contact_phone=phone,
                        location=location,
                        direction="inbound",
                        status="received",
                        body="Got it, thanks!",
                        created_at=sent_at + timedelta(hours=random.randint(1, 20)),
                    )
                )

        for i in range(200):
            sent_at = now - timedelta(days=random.randint(0, 45))
            email = f"parent{i % 60}@example.com"
            location = random.choice(LOCATIONS)
            db.add(
                EmailEvent(
                    email=email,
                    location=location,
                    program_tier=random.choice(TIERS),
                    event_type="sent",
                    subject="This week's practice schedule",
                    created_at=sent_at,
                )
            )
            if random.random() < 0.5:
                db.add(
                    EmailEvent(
                        email=email,
                        location=location,
                        event_type="opened",
                        created_at=sent_at + timedelta(hours=random.randint(1, 30)),
                    )
                )
            if random.random() < 0.15:
                db.add(
                    EmailEvent(
                        email=email,
                        location=location,
                        event_type="clicked",
                        created_at=sent_at + timedelta(hours=random.randint(1, 30)),
                    )
                )
        db.commit()
        print("Seeded demo data.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
