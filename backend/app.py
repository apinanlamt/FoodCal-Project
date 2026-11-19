from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import create_access_token, decode_access_token, hash_password, verify_password
from backend.database import Food, Meal, User, get_session, initialize_database
from backend.demo_accounts import DEMO_USERS, demo_login_enabled
from backend.inference import ModelNotReadyError, predict_food


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: FastAPI):
    from backend.auth import get_jwt_secret

    get_jwt_secret()
    initialize_database()
    yield


app = FastAPI(
    title="FoodCal API",
    description="Food image classification, local account authentication, approximate nutrition and meal history.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class CreateMealRequest(BaseModel):
    food_id: int
    servings_g: float = Field(gt=0, le=2000)
    confidence: float = Field(ge=0, le=1)
    predicted_label: str = Field(min_length=1, max_length=160)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise HTTPException(status_code=422, detail="กรุณาระบุอีเมลให้ถูกต้อง")
    return normalized


def _user_response(user: User) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_session),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนใช้งาน")
    claims = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if not claims or not isinstance(claims.get("sub"), str):
        raise HTTPException(status_code=401, detail="เซสชันหมดอายุหรือไม่ถูกต้อง กรุณาเข้าสู่ระบบใหม่")
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="บัญชีนี้ไม่พร้อมใช้งาน กรุณาติดต่อผู้ดูแลระบบ")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="เฉพาะผู้ดูแลระบบเท่านั้นที่ทำรายการนี้ได้")
    return current_user


@app.get("/api/auth/demo-users")
def get_demo_users() -> list[dict[str, str]]:
    if not demo_login_enabled():
        raise HTTPException(status_code=404, detail="ไม่เปิดบัญชีทดลอง")
    return [
        {
            "email": user["email"],
            "display_name": user["display_name"],
            "password": user["password"],
        }
        for user in DEMO_USERS
    ]


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_session)) -> dict[str, object]:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "expires_in": 12 * 60 * 60,
        "user": _user_response(user),
    }


@app.get("/api/auth/me")
def current_account(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    return _user_response(current_user)


@app.post("/api/auth/users", status_code=201)
def create_user(
    payload: CreateUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_session),
) -> dict[str, str]:
    email = _normalize_email(payload.email)
    existing_user = db.scalar(select(User.id).where(User.email == email))
    if existing_user:
        raise HTTPException(status_code=409, detail="อีเมลนี้มีบัญชีอยู่แล้ว")
    user = User(
        id=str(uuid4()),
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user)


def _nutrition(food: Food, servings_g: float) -> dict[str, float]:
    multiplier = servings_g / 100
    return {
        "calories_kcal": round(food.calories_kcal * multiplier, 1),
        "protein_g": round(food.protein_g * multiplier, 1),
        "carbs_g": round(food.carbs_g * multiplier, 1),
        "fat_g": round(food.fat_g * multiplier, 1),
    }


def _food_for_label(db: Session, label: str) -> Food | None:
    normalized_label = label.casefold().replace("-", " ").replace("_", " ").strip()
    foods = db.scalars(select(Food)).all()
    for food in foods:
        candidates = [food.food_key, food.name, *(food.aliases or "").split(",")]
        for candidate in candidates:
            normalized_candidate = candidate.casefold().replace("-", " ").replace("_", " ").strip()
            if normalized_label == normalized_candidate:
                return food
    return None


@app.get("/health")
def health() -> dict[str, object]:
    model_path = Path(os.getenv("MODEL_PATH", str(PROJECT_ROOT / "backend" / "model" / "foodcal.pt")))
    return {
        "status": "ok",
        "model_available": model_path.is_file(),
        "database": "configured",
    }


@app.get("/api/foods")
def list_foods(
    q: Annotated[str | None, Query(max_length=100)] = None,
    db: Session = Depends(get_session),
) -> list[dict[str, object]]:
    foods = db.scalars(select(Food).order_by(Food.name)).all()
    query = q.casefold().strip() if q else ""
    return [
        {"id": food.id, "food_key": food.food_key, "name": food.name}
        for food in foods
        if not query or query in food.name.casefold() or query in food.food_key.casefold()
    ]


@app.post("/api/predict")
def predict(
    file: Annotated[UploadFile, File(description="Food image (JPEG, PNG or WebP)")],
    servings_g: Annotated[float, Form(gt=0, le=2000)] = 250,
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict[str, object]:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="ไฟล์ที่ส่งมาต้องเป็นรูปภาพ")
    raw_image = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(raw_image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="รูปภาพต้องมีขนาดไม่เกิน 8 MB")
    try:
        with Image.open(BytesIO(raw_image)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="รองรับเฉพาะ JPEG, PNG และ WebP")
            source.verify()
        with Image.open(BytesIO(raw_image)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="ความละเอียดรูปภาพสูงเกินไป")
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="ไม่สามารถอ่านไฟล์รูปภาพนี้ได้") from None

    try:
        label, confidence = predict_food(image)
    except ModelNotReadyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    food = _food_for_label(db, label)
    nutrition = _nutrition(food, servings_g) if food else None
    return {
        "predicted_label": label,
        "food_id": food.id if food else None,
        "food_name": food.name if food else label.replace("_", " ").title(),
        "confidence": round(confidence, 5),
        "servings_g": round(servings_g, 1),
        "nutrition": nutrition,
    }


@app.post("/api/meals", status_code=201)
def create_meal(
    payload: CreateMealRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    food = db.get(Food, payload.food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="ไม่พบอาหารในฐานข้อมูล")
    nutrition = _nutrition(food, payload.servings_g)
    meal = Meal(
        owner_id=current_user.id,
        food_id=food.id,
        food_name=food.name,
        predicted_label=payload.predicted_label,
        confidence=payload.confidence,
        servings_g=payload.servings_g,
        **nutrition,
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return _meal_response(meal)


def _meal_response(meal: Meal) -> dict[str, object]:
    return {
        "id": meal.id,
        "food_name": meal.food_name,
        "predicted_label": meal.predicted_label,
        "confidence": meal.confidence,
        "servings_g": meal.servings_g,
        "calories_kcal": meal.calories_kcal,
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "created_at": meal.created_at.isoformat() if meal.created_at else None,
    }


@app.get("/api/meals")
def list_meals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[dict[str, object]]:
    meals = db.scalars(
        select(Meal)
        .where(Meal.owner_id == current_user.id)
        .order_by(Meal.created_at.desc(), Meal.id.desc())
        .limit(100)
    ).all()
    return [_meal_response(meal) for meal in meals]


@app.delete("/api/meals/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    meal = db.scalar(select(Meal).where(Meal.id == meal_id, Meal.owner_id == current_user.id))
    if meal is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการมื้อนี้")
    db.delete(meal)
    db.commit()