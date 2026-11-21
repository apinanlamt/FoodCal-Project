from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import Food, Meal, get_session, initialize_database
from backend.inference import ModelNotReadyError, model_availability, model_info, predict_food, predict_food_auto


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
PROJECT_ROOT = Path(__file__).resolve().parents[1]
with (PROJECT_ROOT / "backend" / "model" / "usda_fndds_mappings.json").open(encoding="utf-8") as nutrition_file:
    NUTRITION_REFERENCE = json.load(nutrition_file)
with (PROJECT_ROOT / "backend" / "model" / "thfood50_nutrition.json").open(encoding="utf-8") as nutrition_file:
    THFOOD50_NUTRITION = json.load(nutrition_file)
THFOOD50_LABEL_MAP = THFOOD50_NUTRITION["class_to_food_key"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="FoodCal API",
    description="Food image classification, approximate nutrition and meal history.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class CreateMealRequest(BaseModel):
    food_id: int
    servings_g: float = Field(gt=0, le=2000)
    confidence: float = Field(ge=0, le=1)
    predicted_label: str = Field(min_length=1, max_length=160)


def _nutrition(food: Food, servings_g: float) -> dict[str, float | None]:
    multiplier = servings_g / 100
    return {
        "calories_kcal": round(food.calories_kcal * multiplier, 1),
        "protein_g": round(food.protein_g * multiplier, 1) if food.protein_g is not None else None,
        "carbs_g": round(food.carbs_g * multiplier, 1) if food.carbs_g is not None else None,
        "fat_g": round(food.fat_g * multiplier, 1) if food.fat_g is not None else None,
    }


def _nutrition_source(food_key: str) -> dict[str, object]:
    thai_food_key = THFOOD50_LABEL_MAP.get(food_key, food_key)
    thai_item = THFOOD50_NUTRITION["foods"].get(thai_food_key)
    if thai_item:
        metadata = THFOOD50_NUTRITION["_meta"]
        return {
            "source": metadata["source"],
            "source_item": metadata["source_item"],
            "data_type": metadata["data_type"],
            "release_date": metadata["release_date"],
            "reference_serving": f"{thai_item['serving_g']:g} g serving",
            "reference_serving_g": thai_item["serving_g"],
            "match_quality": thai_item["match_quality"],
            "match_note": thai_item["match_note"],
            "verified": thai_item["match_quality"] == "direct",
        }
    if food_key == "PadThai":
        food_key = "pad_thai"
    item = NUTRITION_REFERENCE.get(food_key, {})
    return {
        "source": item.get("source", "Unverified estimate"),
        "fdc_id": item.get("fdc_id"),
        "fdc_description": item.get("fdc_description"),
        "source_item": item.get("source_item"),
        "data_type": item.get("data_type"),
        "release_date": item.get("release_date"),
        "reference_serving": item.get("serving"),
        "reference_serving_g": item.get("serving_g"),
        "match_quality": item.get("match_quality", "unverified"),
        "verified": bool(item.get("verified", False)),
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


def _nutrition_lookup_label(model_name: str, label: str) -> str:
    if model_name == "thfood50":
        return THFOOD50_LABEL_MAP.get(label, label)
    return label


def _display_label(label: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", label.replace("_", " "))
    return spaced.strip().title()


@app.get("/health")
def health() -> dict[str, object]:
    models = model_availability()
    return {
        "status": "ok",
        "model_available": models["food101"],
        "models": models,
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
    model_name: Annotated[str, Form()] = "auto",
    db: Session = Depends(get_session),
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
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="ไม่สามารถอ่านไฟล์รูปภาพนี้ได้") from None

    try:
        if model_name == "auto":
            model_name, label, confidence, top_predictions, selection_reason = predict_food_auto(image)
            selection_mode = "automatic"
        else:
            selection_reason = "เลือกโมเดลโดยผู้ใช้"
            selection_mode = "manual"
            label, confidence, top_predictions = predict_food(image, model_name)
        info = model_info(model_name)
    except ModelNotReadyError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    nutrition_label = _nutrition_lookup_label(model_name, label)
    food = _food_for_label(db, nutrition_label)
    nutrition = _nutrition(food, servings_g) if food else None
    ranked_predictions = []
    for candidate_label, score in top_predictions:
        candidate_food = _food_for_label(db, _nutrition_lookup_label(model_name, candidate_label))
        ranked_predictions.append({
            "label": candidate_label,
            "food_name": candidate_food.name if candidate_food else _display_label(candidate_label),
            "score": round(score, 5),
        })
    return {
        "model": model_name,
        **info,
        "selection_mode": selection_mode,
        "selection_reason": selection_reason,
        "predicted_label": label,
        "food_id": food.id if food else None,
        "food_name": food.name if food else _display_label(label),
        "confidence": round(confidence, 5),
        "top_predictions": ranked_predictions,
        "servings_g": round(servings_g, 1),
        "nutrition": nutrition,
        "nutrition_per_100g": {
            "calories_kcal": food.calories_kcal,
            "protein_g": food.protein_g,
            "carbs_g": food.carbs_g,
            "fat_g": food.fat_g,
        } if food else None,
        "nutrition_source": _nutrition_source(nutrition_label),
    }


@app.post("/api/meals", status_code=201)
def create_meal(
    payload: CreateMealRequest,
    db: Session = Depends(get_session),
) -> dict[str, object]:
    food = db.get(Food, payload.food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="ไม่พบอาหารในฐานข้อมูล")
    nutrition = _nutrition(food, payload.servings_g)
    meal = Meal(
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
        "nutrition_source": _nutrition_source(meal.predicted_label),
        "created_at": meal.created_at.isoformat() if meal.created_at else None,
    }


@app.get("/api/meals")
def list_meals(
    db: Session = Depends(get_session),
) -> list[dict[str, object]]:
    meals = db.scalars(
        select(Meal)
        .order_by(Meal.created_at.desc(), Meal.id.desc())
        .limit(100)
    ).all()
    return [_meal_response(meal) for meal in meals]


@app.delete("/api/meals/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_session),
) -> None:
    meal = db.get(Meal, meal_id)
    if meal is None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการมื้อนี้")
    db.delete(meal)
    db.commit()
