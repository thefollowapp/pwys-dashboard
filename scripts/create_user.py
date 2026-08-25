"""Create or reset a dashboard user account.

Usage:
    python scripts/create_user.py "keith@playwhereyoustay.org" "Keith" --admin
    python scripts/create_user.py "ryates051@gmail.com" "Robby" --password "custom-password" --admin

If --password is omitted, a random temporary password is generated and printed once.
Run this from the project root with the venv active.
"""

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset a PWYS dashboard user")
    parser.add_argument("email")
    parser.add_argument("name")
    parser.add_argument("--password", default=None, help="Set a specific password (otherwise a random one is generated)")
    parser.add_argument("--admin", action="store_true", help="Grant admin flag")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    email = args.email.strip().lower()
    password = args.password or secrets.token_urlsafe(9)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.password_hash = hash_password(password)
            user.name = args.name
            user.is_admin = args.admin
            action = "Updated"
        else:
            user = User(email=email, name=args.name, password_hash=hash_password(password), is_admin=args.admin)
            db.add(user)
            action = "Created"
        db.commit()
    finally:
        db.close()

    print(f"{action} user {email}")
    if not args.password:
        print(f"Temporary password: {password}")
        print("Share this with them out-of-band and have them change it from the Account page after logging in.")


if __name__ == "__main__":
    main()
