# FoodCal model files

The local demo includes two selectable ONNX image classifiers:

- **Food-101 (101 classes):** `food101_effnetb0.onnx`, external tensor data `food101_effnetb0.onnx.data`, and class order `classes.json`.
- **THFOOD-50 (50 classes):** `thfood50_effnetb0.onnx` and class order `classes_thfood50.json`. This exported ONNX is self-contained and does not need a `.onnx.data` sidecar.

Both models take normalized RGB tensors shaped `[batch, 3, 224, 224]`. Preprocessing resizes the shorter image edge to 256, center-crops to 224, converts pixels to `[0, 1]`, then applies ImageNet mean/std normalization. Class JSON ordering must match each model's output logits exactly.

The app asks the user to select Food-101 or THFOOD-50 before prediction. Confidence scores from the two classifiers are not calibrated to each other and must not be compared across models.

`usda_fndds_mappings.json` contains a curated snapshot of USDA FNDDS 2021–2023 and SR Legacy mapped to Food-101 labels. Nutrition for the THFOOD-50 model is only shown when a class has a corresponding entry in the existing database; currently Pad Thai is mapped to the USDA Pad Thai entry. Other Thai predictions remain classification-only instead of receiving invented calorie values.
