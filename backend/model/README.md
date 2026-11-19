# FoodCal model files

Place the trained **TorchScript** model at `foodcal.pt`. Replace `classes.json` with the exact class labels in the same order as the model output. Update the image size, resize strategy, and normalization constants in `../inference.py` to match the training pipeline.

The checked-in `classes.json` is only a scaffold. It does not contain trained weights or represent predictions. Do not report calorie estimates as real model results until the trained model has been installed and verified.