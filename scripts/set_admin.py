"""Grant or revoke admin access for an existing dashboard user, without touching their
password (unlike create_user.py, which always resets it).

Usage:
    python scripts/set_admin.py "keith@playwhereyoustay.org" --admin
    python scripts/set_admin.py "keith@playwhereyoustay.org" --no-admin

Run this from the project root with the venv active.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or revoke admin access for a PWYS dashboard user")
    parser.add_argument("email")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--admin", action="store_true", help="Grant admin access")
    group.add_argument("--no-admin", action="store_true", help="Revoke admin access")
    args = parser.parse_args()

    email = args.email.strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"No user found with email {email}")
            return
        user.is_admin = args.admin
        db.commit()
        print(f"{'Granted' if args.admin else 'Revoked'} admin access for {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
