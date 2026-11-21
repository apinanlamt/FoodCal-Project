from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine, inspect, select, text
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
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    aliases: Mapped[str] = mapped_column(String(500), default="")


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"))
    food_name: Mapped[str] = mapped_column(String(160))
    predicted_label: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[float] = mapped_column(Float)
    servings_g: Mapped[float] = mapped_column(Float)
    calories_kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_macro_columns_nullable() -> None:
    """Allow calorie-only foods while preserving saved meal records."""
    columns = ("protein_g", "carbs_g", "fat_g")
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            for table in ("foods", "meals"):
                for column in columns:
                    connection.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL"))
        return

    if engine.dialect.name != "sqlite":
        raise RuntimeError(f"Unsupported database dialect for nullable nutrition migration: {engine.dialect.name}")

    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        needs_migration = any(
            any(row[1] in columns and row[3] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall())
            for table in ("foods", "meals")
        )
        if not needs_migration:
            return

        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        cursor.execute(
            """CREATE TABLE foods__nullable (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                food_key VARCHAR(120) NOT NULL,
                name VARCHAR(160) NOT NULL,
                calories_kcal FLOAT NOT NULL,
                protein_g FLOAT,
                carbs_g FLOAT,
                fat_g FLOAT,
                aliases VARCHAR(500) NOT NULL
            )"""
        )
        cursor.execute(
            "INSERT INTO foods__nullable SELECT id, food_key, name, calories_kcal, protein_g, carbs_g, fat_g, aliases FROM foods"
        )
        cursor.execute(
            """CREATE TABLE meals__nullable (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                food_id INTEGER NOT NULL,
                food_name VARCHAR(160) NOT NULL,
                predicted_label VARCHAR(160) NOT NULL,
                confidence FLOAT NOT NULL,
                servings_g FLOAT NOT NULL,
                calories_kcal FLOAT NOT NULL,
                protein_g FLOAT,
                carbs_g FLOAT,
                fat_g FLOAT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(food_id) REFERENCES foods (id)
            )"""
        )
        cursor.execute(
            """INSERT INTO meals__nullable
               SELECT id, food_id, food_name, predicted_label, confidence, servings_g,
                      calories_kcal, protein_g, carbs_g, fat_g, created_at FROM meals"""
        )
        cursor.execute("DROP TABLE meals")
        cursor.execute("DROP TABLE foods")
        cursor.execute("ALTER TABLE foods__nullable RENAME TO foods")
        cursor.execute("ALTER TABLE meals__nullable RENAME TO meals")
        cursor.execute("CREATE UNIQUE INDEX ix_foods_food_key ON foods (food_key)")
        cursor.execute("CREATE INDEX ix_meals_created_at ON meals (created_at)")
        connection.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _remove_login_schema() -> None:
    """Drop account linkage while preserving every saved meal."""
    if engine.dialect.name == "sqlite":
        connection = engine.raw_connection()
        try:
            cursor = connection.cursor()
            columns = {row[1] for row in cursor.execute("PRAGMA table_info(meals)").fetchall()}
            has_users = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone() is not None
            if "owner_id" not in columns and not has_users:
                return

            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN")
            if "owner_id" in columns:
                cursor.execute(
                    """CREATE TABLE meals__no_login (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        food_id INTEGER NOT NULL,
                        food_name VARCHAR(160) NOT NULL,
                        predicted_label VARCHAR(160) NOT NULL,
                        confidence FLOAT NOT NULL,
                        servings_g FLOAT NOT NULL,
                        calories_kcal FLOAT NOT NULL,
                        protein_g FLOAT,
                        carbs_g FLOAT,
                        fat_g FLOAT,
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(food_id) REFERENCES foods (id)
                    )"""
                )
                cursor.execute(
                    """INSERT INTO meals__no_login
                       SELECT id, food_id, food_name, predicted_label, confidence, servings_g,
                              calories_kcal, protein_g, carbs_g, fat_g, created_at FROM meals"""
                )
                cursor.execute("DROP TABLE meals")
                cursor.execute("ALTER TABLE meals__no_login RENAME TO meals")
                cursor.execute("CREATE INDEX ix_meals_created_at ON meals (created_at)")
            if has_users:
                cursor.execute("DROP TABLE users")
            connection.commit()
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            meal_columns = {column["name"] for column in inspect(connection).get_columns("meals")}
            if "owner_id" in meal_columns:
                connection.execute(text("ALTER TABLE meals DROP COLUMN owner_id"))
            if inspect(connection).has_table("users"):
                connection.execute(text("DROP TABLE users"))
        return

    raise RuntimeError(f"Unsupported database dialect for login removal: {engine.dialect.name}")


def initialize_database() -> None:
    Base.metadata.create_all(engine)
    _make_macro_columns_nullable()
    _remove_login_schema()
    seed_path = PROJECT_ROOT / "database" / "foods_seed.json"
    with seed_path.open(encoding="utf-8") as seed_file:
        seed_foods = json.load(seed_file)
    nutrition_path = PROJECT_ROOT / "backend" / "model" / "usda_fndds_mappings.json"
    with nutrition_path.open(encoding="utf-8") as nutrition_file:
        nutrition_data = json.load(nutrition_file)
    seed_foods_by_key = {item["food_key"]: item for item in seed_foods}
    for food_key, item in nutrition_data.items():
        if food_key == "_meta":
            continue
        if item.get("match_quality") == "unverified":
            serving_g = float(item["serving_g"])
            if serving_g <= 0:
                raise ValueError(f"Invalid serving size in calories.json for {food_key}")
            calories_per_100g = float(item["kcal"]) * 100 / serving_g
            protein_g = carbs_g = fat_g = None
        else:
            calories_per_100g = float(item["kcal"])
            protein_g = float(item["protein_g"])
            carbs_g = float(item["carbs_g"])
            fat_g = float(item["fat_g"])
        food_seed = seed_foods_by_key.get(
            food_key,
            {"food_key": food_key, "name": food_key.replace("_", " ").title(), "aliases": ""},
        )
        food_seed.update(
            {
                "calories_kcal": calories_per_100g,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
            }
        )
        seed_foods_by_key[food_key] = food_seed

    thai_nutrition_path = PROJECT_ROOT / "backend" / "model" / "thfood50_nutrition.json"
    with thai_nutrition_path.open(encoding="utf-8") as nutrition_file:
        thai_nutrition_data = json.load(nutrition_file)
    for food_key, item in thai_nutrition_data["foods"].items():
        serving_g = float(item["serving_g"])
        if serving_g <= 0:
            raise ValueError(f"Invalid serving size in thfood50_nutrition.json for {food_key}")
        factor = 100 / serving_g
        seed_foods_by_key[food_key] = {
            "food_key": food_key,
            "name": item["name"],
            "aliases": ",".join(item.get("aliases", [])),
            "calories_kcal": float(item["kcal_per_serving"]) * factor,
            "protein_g": float(item["protein_g_per_serving"]) * factor,
            "carbs_g": float(item["carbs_g_per_serving"]) * factor,
            "fat_g": float(item["fat_g_per_serving"]) * factor,
        }
    seed_foods = list(seed_foods_by_key.values())
    with SessionLocal() as session:
        for item in seed_foods:
            food = session.scalar(select(Food).where(Food.food_key == item["food_key"]))
            if food is None:
                session.add(Food(**item))
            else:
                food.name = item["name"]
                food.calories_kcal = item["calories_kcal"]
                food.protein_g = item["protein_g"]
                food.carbs_g = item["carbs_g"]
                food.fat_g = item["fat_g"]
                food.aliases = item["aliases"]
        session.commit()
