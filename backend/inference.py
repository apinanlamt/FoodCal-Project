from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(PROJECT_ROOT / "backend" / "model" / "foodcal.pt")))
CLASSES_PATH = Path(os.getenv("CLASSES_PATH", str(PROJECT_ROOT / "backend" / "model" / "classes.json")))
MODEL_IMAGE_SIZE = int(os.getenv("MODEL_IMAGE_SIZE", "224"))
MODEL_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
MODEL_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)

_model = None
_classes: list[str] | None = None
_model_lock = Lock()


class ModelNotReadyError(RuntimeError):
    """The trained model or its class list is missing or invalid."""


def _load_model():
    global _model, _classes
    if _model is not None and _classes is not None:
        return _model, _classes
    with _model_lock:
        if _model is not None and _classes is not None:
            return _model, _classes
        if not MODEL_PATH.is_file():
            raise ModelNotReadyError(f"ไม่พบโมเดลที่ {MODEL_PATH}; วาง TorchScript model ชื่อ foodcal.pt ก่อนใช้งาน")
        if not CLASSES_PATH.is_file():
            raise ModelNotReadyError(f"ไม่พบไฟล์รายชื่อคลาสที่ {CLASSES_PATH}")
        try:
            with CLASSES_PATH.open(encoding="utf-8") as class_file:
                classes = json.load(class_file)
            if not isinstance(classes, list) or not classes or not all(isinstance(item, str) for item in classes):
                raise ValueError("classes.json ต้องเป็น JSON array ที่มีชื่อคลาสเป็นข้อความ")
            import torch

            model = torch.jit.load(str(MODEL_PATH), map_location="cpu")
            model.eval()
        except Exception as error:
            raise ModelNotReadyError(f"โหลดโมเดลหรือ classes.json ไม่สำเร็จ: {error}") from error
        _model = model
        _classes = classes
        return _model, _classes


def predict_food(image: Image.Image) -> tuple[str, float]:
    model, classes = _load_model()
    import torch

    resized = image.convert("RGB").resize((MODEL_IMAGE_SIZE, MODEL_IMAGE_SIZE), Image.Resampling.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float32) / 255.0
    normalized = (pixels - MODEL_MEAN) / MODEL_STD
    tensor = torch.from_numpy(normalized.transpose(2, 0, 1).copy()).unsqueeze(0)
    try:
        with torch.inference_mode():
            output = model(tensor)
        if isinstance(output, dict):
            output = next(iter(output.values()))
        elif isinstance(output, (tuple, list)):
            output = output[0]
        if not isinstance(output, torch.Tensor) or output.ndim != 2 or output.shape[0] != 1:
            raise ValueError("โมเดลต้องคืน logits ในรูป tensor ขนาด [1, จำนวนคลาส]")
        if output.shape[1] != len(classes):
            raise ValueError(f"จำนวน output ({output.shape[1]}) ไม่ตรงกับจำนวนคลาส ({len(classes)})")
        probabilities = torch.softmax(output[0], dim=0)
        index = int(torch.argmax(probabilities).item())
        return classes[index], float(probabilities[index].item())
    except Exception as error:
        raise ModelNotReadyError(f"ประมวลผลรูปด้วยโมเดลไม่สำเร็จ: {error}") from error