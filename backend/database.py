from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{PROJECT_ROOT / 'data' / 'foodcal.db'}"
database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine_options = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
if database_url.startswith("sqlite:///"):
    sqlite_path = Path(database_url.removeprefix("sqlite:///"))
    if str(sqlite_path) not in {":memory:", "file::memory:"}:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(database_url, pool_pre_ping=True, connect_args=engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    calories_kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    aliases: Mapped[str] = mapped_column(String(500), default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"))
    food_name: Mapped[str] = mapped_column(String(160))
    predicted_label: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[float] = mapped_column(Float)
    servings_g: Mapped[float] = mapped_column(Float)
    calories_kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def initialize_database() -> None:
    Base.metadata.create_all(engine)
    seed_path = PROJECT_ROOT / "database" / "foods_seed.json"
    with seed_path.open(encoding="utf-8") as seed_file:
        seed_foods = json.load(seed_file)
    with SessionLocal() as session:
        for item in seed_foods:
            exists = session.scalar(select(Food.id).where(Food.food_key == item["food_key"]))
            if exists is None:
                session.add(Food(**item))
        session.commit()

    from backend.auth import hash_password
    from backend.demo_accounts import DEMO_USERS, demo_login_enabled

    if demo_login_enabled():
        with SessionLocal() as session:
            for demo_user in DEMO_USERS:
                exists = session.scalar(select(User.id).where(User.email == demo_user["email"]))
                if exists is None:
                    session.add(
                        User(
                            id=str(uuid4()),
                            email=demo_user["email"],
                            display_name=demo_user["display_name"],
                            password_hash=hash_password(demo_user["password"]),
                            role="user",
                            is_active=True,
                        )
                    )
            session.commit()