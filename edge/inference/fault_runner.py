"""
Edge-local Fault inference — same 2-stage pipeline as
`backend/app/services/fault_service.py`, but running the ONNX-exported
models via `onnxruntime` instead of `lightgbm` + `joblib`, so a
constrained edge device doesn't need the full LightGBM/scikit-learn
wheels installed. Feature engineering (`piston_to_uav_telemetry`,
`extract_window_features`) is imported directly from the backend's own
adapter module — it's a pure numpy/scipy function with no FastAPI/DB
dependency, so re-implementing it here would just be a second copy to
keep in sync for no benefit.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from typing import Optional

import numpy as np
import onnxruntime as ort

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BACKEND_ROOT = os.path.join(_REPO_ROOT, "backend")
for p in (_REPO_ROOT, _BACKEND_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.fault_adapter import piston_to_uav_telemetry, extract_window_features  # noqa: E402

_MODELS_DIR = os.path.join(_REPO_ROOT, "ml", "models")

FAULT_CLASSES = {
    0: "No Failure",
    1: "RC Failure",
    2: "GPS Failure",
    3: "Accelerometer Failure",
    4: "Gyro Failure",
    5: "Compass Failure",
    6: "Barometer Failure",
}


class EdgeFaultRunner:
    def __init__(self, window_len: int = 80, models_dir: str = _MODELS_DIR):
        self._window_len = window_len
        self._windows: dict = collections.defaultdict(lambda: collections.deque(maxlen=window_len))
        self._prev_vibes: dict = {}

        with open(os.path.join(models_dir, "fault_feature_names.json")) as f:
            self._feature_names = json.load(f)

        self._stage1 = ort.InferenceSession(os.path.join(models_dir, "fault_stage1.onnx"))
        self._stage2 = ort.InferenceSession(os.path.join(models_dir, "fault_stage2.onnx"))

    def push_reading(self, engine_id: str, raw_telemetry: dict) -> Optional[dict]:
        prev_vibe = self._prev_vibes.get(engine_id)
        current_vibe = {
            "x": raw_telemetry.get("vibration_x", 0.0),
            "y": raw_telemetry.get("vibration_y", 0.0),
            "z": raw_telemetry.get("vibration_z", 0.0),
        }
        uav_row = piston_to_uav_telemetry(raw_telemetry, prev_vibe)
        self._prev_vibes[engine_id] = current_vibe

        window = self._windows[engine_id]
        window.append(uav_row)
        if len(window) < self._window_len:
            return None

        features = extract_window_features(np.array(window)).reshape(1, -1).astype(np.float32)

        s1_labels, s1_probs = self._stage1.run(None, {"input": features})
        is_fault = int(s1_labels[0])

        if is_fault == 0:
            conf = float(s1_probs[0][0])
            return {
                "class_id": 0,
                "fault_class": "No Failure",
                "confidence": conf,
                "probabilities": [conf, 1 - conf, 0.0, 0.0, 0.0, 0.0, 0.0],
            }

        s2_labels, s2_probs = self._stage2.run(None, {"input": features})
        probs_row = s2_probs[0]
        prob_values = [probs_row[k] for k in sorted(probs_row)]
        class_id = int(s2_labels[0])
        if class_id not in FAULT_CLASSES:
            class_id = 0

        return {
            "class_id": class_id,
            "fault_class": FAULT_CLASSES[class_id],
            "confidence": float(max(prob_values)),
            "probabilities": [0.0] + [float(p) for p in prob_values],
        }
