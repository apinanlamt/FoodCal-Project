from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(
    os.getenv("MODEL_PATH", str(PROJECT_ROOT / "backend" / "model" / "food101_effnetb0.onnx"))
)
CLASSES_PATH = Path(os.getenv("CLASSES_PATH", str(PROJECT_ROOT / "backend" / "model" / "classes.json")))
MODEL_IMAGE_SIZE = int(os.getenv("MODEL_IMAGE_SIZE", "224"))
MODEL_RESIZE_SIZE = int(os.getenv("MODEL_RESIZE_SIZE", "256"))
MODEL_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
MODEL_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
# Automatic routing uses THFOOD-50's own score and top-two margin. Scores from
# Food-101 and THFOOD-50 are not calibrated against each other.
THFOOD50_AUTO_MIN_CONFIDENCE = float(os.getenv("THFOOD50_AUTO_MIN_CONFIDENCE", "0.50"))
THFOOD50_AUTO_MIN_MARGIN = float(os.getenv("THFOOD50_AUTO_MIN_MARGIN", "0.10"))

MODEL_SPECS = {
    "food101": {
        "name": "Food-101",
        "path": MODEL_PATH,
        "classes_path": CLASSES_PATH,
    },
    "thfood50": {
        "name": "THFOOD-50",
        "path": Path(os.getenv("THFOOD50_MODEL_PATH", str(PROJECT_ROOT / "backend" / "model" / "thfood50_effnetb0.onnx"))),
        "classes_path": Path(os.getenv("THFOOD50_CLASSES_PATH", str(PROJECT_ROOT / "backend" / "model" / "classes_thfood50.json"))),
    },
}
_models: dict[str, tuple[object, list[str], str, str]] = {}
_model_lock = Lock()


class ModelNotReadyError(RuntimeError):
    """The ONNX model or its class list is missing or invalid."""


def _load_model(model_name: str = "food101"):
    if model_name not in MODEL_SPECS:
        raise ModelNotReadyError("เลือกรุ่นโมเดลไม่ถูกต้อง")
    if model_name in _models:
        return _models[model_name]
    with _model_lock:
        if model_name in _models:
            return _models[model_name]
        spec = MODEL_SPECS[model_name]
        model_path = spec["path"]
        classes_path = spec["classes_path"]
        if not model_path.is_file():
            raise ModelNotReadyError(f"ไม่พบโมเดล {spec['name']} ที่ {model_path}")
        if not classes_path.is_file():
            raise ModelNotReadyError(f"ไม่พบไฟล์รายชื่อคลาสของ {spec['name']} ที่ {classes_path}")
        try:
            with classes_path.open(encoding="utf-8") as class_file:
                classes = json.load(class_file)
            if not isinstance(classes, list) or not classes or not all(isinstance(item, str) for item in classes):
                raise ValueError("classes.json ต้องเป็น JSON array ที่มีชื่อคลาสเป็นข้อความ")

            import onnxruntime as ort

            model = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
            inputs = model.get_inputs()
            outputs = model.get_outputs()
            if len(inputs) != 1 or len(outputs) != 1:
                raise ValueError("โมเดลต้องมี input และ output อย่างละหนึ่งรายการ")
            if len(inputs[0].shape) != 4 or inputs[0].shape[1:] != [3, MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE]:
                raise ValueError(
                    f"รูปแบบ input ของโมเดลไม่ตรงกับ [batch, 3, {MODEL_IMAGE_SIZE}, {MODEL_IMAGE_SIZE}]: "
                    f"{inputs[0].shape}"
                )
            if len(outputs[0].shape) != 2 or outputs[0].shape[-1] not in (len(classes), "classes"):
                raise ValueError(
                    f"จำนวน output ของโมเดลไม่ตรงกับจำนวนคลาส ({len(classes)}): {outputs[0].shape}"
                )
        except Exception as error:
            raise ModelNotReadyError(f"โหลด ONNX model หรือ classes.json ไม่สำเร็จ: {error}") from error
        _models[model_name] = (model, classes, inputs[0].name, outputs[0].name)
        return _models[model_name]


def model_info(model_name: str) -> dict[str, object]:
    model, classes, _, _ = _load_model(model_name)
    return {"model_name": MODEL_SPECS[model_name]["name"], "class_count": len(classes)}


def model_availability() -> dict[str, bool]:
    return {name: spec["path"].is_file() and spec["classes_path"].is_file() for name, spec in MODEL_SPECS.items()}


def predict_food(image: Image.Image, model_name: str = "food101") -> tuple[str, float, list[tuple[str, float]]]:
    model, classes, input_name, output_name = _load_model(model_name)
    image = image.convert("RGB")
    width, height = image.size
    if width <= height:
        resize_width = MODEL_RESIZE_SIZE
        resize_height = int(MODEL_RESIZE_SIZE * height / width)
    else:
        resize_height = MODEL_RESIZE_SIZE
        resize_width = int(MODEL_RESIZE_SIZE * width / height)
    resized = image.resize((resize_width, resize_height), Image.Resampling.BILINEAR)
    left = int(round((resize_width - MODEL_IMAGE_SIZE) / 2.0))
    top = int(round((resize_height - MODEL_IMAGE_SIZE) / 2.0))
    cropped = resized.crop((left, top, left + MODEL_IMAGE_SIZE, top + MODEL_IMAGE_SIZE))
    pixels = np.asarray(cropped, dtype=np.float32) / 255.0
    normalized = (pixels - MODEL_MEAN) / MODEL_STD
    tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1)[None, ...], dtype=np.float32)
    try:
        output = model.run([output_name], {input_name: tensor})[0]
        if not isinstance(output, np.ndarray) or output.ndim != 2 or output.shape[0] != 1:
            raise ValueError("โมเดลต้องคืน logits ขนาด [1, จำนวนคลาส]")
        if output.shape[1] != len(classes):
            raise ValueError(f"จำนวน output ({output.shape[1]}) ไม่ตรงกับจำนวนคลาส ({len(classes)})")
        logits = output[0].astype(np.float64)
        probabilities = np.exp(logits - np.max(logits))
        probabilities /= probabilities.sum()
        top_indices = np.argsort(probabilities)[-3:][::-1]
        top_predictions = [(classes[int(index)], float(probabilities[index])) for index in top_indices]
        label, score = top_predictions[0]
        return label, score, top_predictions
    except Exception as error:
        raise ModelNotReadyError(f"ประมวลผลรูปด้วย ONNX model ไม่สำเร็จ: {error}") from error


def predict_food_auto(
    image: Image.Image,
) -> tuple[str, str, float, list[tuple[str, float]], str]:
    """Run available classifiers and route to a model using a conservative THFOOD gate."""
    available = [name for name in MODEL_SPECS if MODEL_SPECS[name]["path"].is_file() and MODEL_SPECS[name]["classes_path"].is_file()]
    if not available:
        raise ModelNotReadyError("ไม่พบไฟล์โมเดลและรายชื่อคลาสของ Food-101 หรือ THFOOD-50")

    predictions: dict[str, tuple[str, float, list[tuple[str, float]]]] = {}
    failures: list[str] = []
    for model_name in available:
        try:
            predictions[model_name] = predict_food(image, model_name)
        except ModelNotReadyError as error:
            failures.append(f"{MODEL_SPECS[model_name]['name']}: {error}")

    if not predictions:
        raise ModelNotReadyError("โหลดโมเดลที่มีอยู่ไม่สำเร็จ: " + "; ".join(failures))

    if len(predictions) == 1:
        model_name, (label, confidence, top_predictions) = next(iter(predictions.items()))
        return model_name, label, confidence, top_predictions, "ใช้โมเดลที่พร้อมใช้งาน"

    thai_label, thai_confidence, thai_predictions = predictions["thfood50"]
    thai_margin = thai_confidence - (thai_predictions[1][1] if len(thai_predictions) > 1 else 0.0)
    if thai_confidence >= THFOOD50_AUTO_MIN_CONFIDENCE and thai_margin >= THFOOD50_AUTO_MIN_MARGIN:
        return "thfood50", thai_label, thai_confidence, thai_predictions, "THFOOD-50 ผ่านเกณฑ์คัดเลือกอัตโนมัติ"

    label, confidence, top_predictions = predictions["food101"]
    return "food101", label, confidence, top_predictions, "THFOOD-50 ไม่ผ่านเกณฑ์ จึงใช้ Food-101"
