# FoodCal model files

The local demo includes two selectable ONNX image classifiers:

- **Food-101 (101 classes):** `food101_effnetb0.onnx`, external tensor data `food101_effnetb0.onnx.data`, and class order `classes.json`.
- **THFOOD-50 (50 classes):** `thfood50_effnetb0.onnx` and class order `classes_thfood50.json`. This exported ONNX is self-contained and does not need a `.onnx.data` sidecar.

Both models take normalized RGB tensors shaped `[batch, 3, 224, 224]`. Preprocessing resizes the shorter image edge to 256, center-crops to 224, converts pixels to `[0, 1]`, then applies ImageNet mean/std normalization. Class JSON ordering must match each model's output logits exactly.

The app runs both available classifiers and automatically routes to THFOOD-50 when its top score is at least 0.50 and its margin over second place is at least 0.10; otherwise it uses Food-101. These are initial, configurable heuristics (`THFOOD50_AUTO_MIN_CONFIDENCE`, `THFOOD50_AUTO_MIN_MARGIN`) and should be tuned against a representative validation set. Confidence scores from the two classifiers are not calibrated to each other and must not be compared across models. If only one model is available, the app uses that model.

`usda_fndds_mappings.json` contains a curated snapshot of USDA FNDDS 2021–2023 and SR Legacy mapped to Food-101 labels.

`thfood50_nutrition.json` maps supported THFOOD-50 class labels to Thai one-dish nutrition records from the Department of Health, Ministry of Public Health. Entries are recorded per reference serving and converted to per-100-g values when the database is initialized. Exact dish matches are marked `direct`; related dishes (for example a class that omits rice while its reference record includes rice) are marked `approximate` and shown as such in the UI. Classes without a defensible match remain classification-only. Source report: https://nutrition2.anamai.moph.go.th/web-upload/6x22caac0452648c8dd1f534819ba2f16c/m_document/32006/14552/file_download/b1e88d991fb8a07533dfcbe1467774a6.pdf
