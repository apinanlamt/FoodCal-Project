from __future__ import annotations

import argparse
import re
from getpass import getpass
from uuid import uuid4

from sqlalchemy import select

from backend.auth import hash_password
from backend.database import SessionLocal, User, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first FoodCal administrator account.")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--name", default="FoodCal Admin", help="Admin display name")
    args = parser.parse_args()
    email = args.email.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        parser.error("Please provide a valid email address")

    password = getpass("Admin password (at least 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12:
        parser.error("Password must contain at least 12 characters")
    if password != confirmation:
        parser.error("Passwords do not match")

    initialize_database()
    with SessionLocal() as session:
        existing_admin = session.scalar(select(User.id).where(User.role == "admin"))
        if existing_admin:
            parser.error("An admin already exists; refusing to create another bootstrap admin")
        if session.scalar(select(User.id).where(User.email == email)):
            parser.error("This email already has an account")
        session.add(
            User(
                id=str(uuid4()),
                email=email,
                display_name=args.name.strip() or "FoodCal Admin",
                password_hash=hash_password(password),
                role="admin",
                is_active=True,
            )
        )
        session.commit()
    print(f"Admin account created: {email}")


if __name__ == "__main__":
    main()