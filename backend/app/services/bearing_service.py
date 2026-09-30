"""
bearing_service.py

Real-time bearing/vibration health inference using Model 3 CNN.

Pipeline per telemetry reading:
  1. Extract vibration_magnitude + rpm from raw telemetry.
  2. Adapter: synthesise + normalise → (1, 32, 32, 1).
  3. CNN inference → 10-element softmax vector.
  4. Argmax → class_id → class_label (via label_mapping.json).
  5. class_label → fault_location + severity_inches (via fault_information.json).
  6. Return rich prediction dict to ingestion service.

Model artifacts (all from ml/training/bearing_model/):
  - model3_bearing_health.keras   : trained 2D CNN
  - normalization.json            : training mean/std (used by adapter)
  - label_mapping.json            : int index → class name
  - fault_information.json        : class name → fault_location + severity_inches
"""

import os
import json
import logging
from typing import Dict, Any, Optional

import numpy as np

from app.services.bearing_adapter import preprocess_to_matrix

logger = logging.getLogger(__name__)

# ── Class mapping hardcoded as fallback (mirrors label_mapping.json) ──
# Index order from training: Ball_007(0), Ball_014(1), Ball_021(2),
# IR_007(3), IR_014(4), IR_021(5), Normal(6), OR_007(7), OR_014(8), OR_021(9)
_FALLBACK_LABEL_MAP: Dict[int, str] = {
    0: "Ball_007", 1: "Ball_014", 2: "Ball_021",
    3: "IR_007",   4: "IR_014",   5: "IR_021",
    6: "Normal",
    7: "OR_007",   8: "OR_014",   9: "OR_021",
}

_FALLBACK_FAULT_INFO: Dict[str, Dict[str, Any]] = {
    "Normal":   {"fault_location": "No fault",              "severity_inches": None},
    "Ball_007": {"fault_location": "Ball / Rolling Element", "severity_inches": 0.007},
    "Ball_014": {"fault_location": "Ball / Rolling Element", "severity_inches": 0.014},
    "Ball_021": {"fault_location": "Ball / Rolling Element", "severity_inches": 0.021},
    "IR_007":   {"fault_location": "Inner Race",             "severity_inches": 0.007},
    "IR_014":   {"fault_location": "Inner Race",             "severity_inches": 0.014},
    "IR_021":   {"fault_location": "Inner Race",             "severity_inches": 0.021},
    "OR_007":   {"fault_location": "Outer Race",             "severity_inches": 0.007},
    "OR_014":   {"fault_location": "Outer Race",             "severity_inches": 0.014},
    "OR_021":   {"fault_location": "Outer Race",             "severity_inches": 0.021},
}


class BearingService:
    """
    Singleton inference service for Model 3 — Bearing / Vibration Health CNN.
    Loads TensorFlow lazily on first prediction to avoid slow startup.
    Falls back to mock predictions if the model file is missing.
    """

    def __init__(self) -> None:
        self._loaded: bool = False
        self._model = None          # tf.keras.Model
        self._label_map: Dict[int, str] = {}
        self._fault_info: Dict[str, Dict] = {}

    # ── Model loading ─────────────────────────────────────────────────
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        base_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "../../../ml/training/bearing_model")
        )
        model_path  = os.path.join(base_dir, "model3_bearing_health.keras")
        label_path  = os.path.join(base_dir, "label_mapping.json")
        fault_path  = os.path.join(base_dir, "fault_information.json")

        # Load JSON metadata first (always required)
        try:
            with open(label_path, "r") as f:
                raw = json.load(f)
                self._label_map = {int(k): v for k, v in raw.items()}
            logger.info("Loaded label_mapping.json (%d classes)", len(self._label_map))
        except Exception as e:
            logger.warning("Could not load label_mapping.json — using hardcoded fallback: %s", e)
            self._label_map = _FALLBACK_LABEL_MAP.copy()

        try:
            with open(fault_path, "r") as f:
                self._fault_info = json.load(f)
            logger.info("Loaded fault_information.json")
        except Exception as e:
            logger.warning("Could not load fault_information.json — using hardcoded fallback: %s", e)
            self._fault_info = _FALLBACK_FAULT_INFO.copy()

        # Load the Keras model (TF imported lazily to avoid slow container startup)
        try:
            import tensorflow as tf
            self._model = tf.keras.models.load_model(model_path, compile=False)
            logger.info("Loaded Model 3 Bearing CNN from %s", model_path)
        except Exception as e:
            logger.error("Failed to load Bearing CNN model — running in mock mode: %s", e)
            self._model = None

        self._loaded = True

    # ── Inference ─────────────────────────────────────────────────────
    def push_reading(
        self, engine_id: str, raw_telemetry: Dict[str, Any], seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run one bearing health prediction from a single telemetry packet.

        Args:
            engine_id:     UUID string for the engine.
            raw_telemetry: dict from MQTT (contains vibration_magnitude, rpm, etc.)
            seed:          optional synthetic-vibration RNG seed (What-If determinism);
                           None = original unseeded behavior.

        Returns:
            dict with keys: class_id, class_label, fault_location,
                            severity_inches, confidence, probabilities
        """
        self._ensure_loaded()

        vib_mag    = float(raw_telemetry.get("vibration_magnitude", 0.3))
        rpm        = float(raw_telemetry.get("rpm", 1772.0))
        fault_hint = str(raw_telemetry.get("fault_type", "none"))

        # ── Mock mode ─────────────────────────────────────────────────
        if self._model is None:
            return self._mock_prediction(vib_mag)

        # ── Real inference ────────────────────────────────────────────
        try:
            # 1. Synthesise + preprocess → (1, 32, 32, 1)
            matrix = preprocess_to_matrix(vib_mag, rpm, fault_hint, seed)

            # 2. CNN forward pass
            probs_raw = self._model.predict(matrix, verbose=0)[0]   # shape (10,)
            probs     = [float(p) for p in probs_raw]

            # 3. Derive class
            class_id    = int(np.argmax(probs_raw))
            confidence  = float(np.max(probs_raw))
            class_label = self._label_map.get(class_id, "Normal")

            # 4. Fault metadata
            info = self._fault_info.get(class_label, {"fault_location": "No fault", "severity_inches": None})

            return {
                "class_id":       class_id,
                "class_label":    class_label,
                "fault_location": info["fault_location"],
                "severity_inches": info["severity_inches"],
                "confidence":     confidence,
                "probabilities":  probs,
            }

        except Exception as e:
            logger.exception("Bearing inference failed for engine %s: %s", engine_id, e)
            return self._mock_prediction(vib_mag)

    # ── Mock / fallback ───────────────────────────────────────────────
    def _mock_prediction(self, vib_mag: float) -> Dict[str, Any]:
        """
        Returns a synthetic 'Normal' prediction when the model is unavailable.
        Escalates to a plausible fault class if vibration is unusually high.
        """
        if vib_mag > 2.0:
            # High vibration → simulate an Outer Race fault at 0.014" severity
            class_id, class_label = 8, "OR_014"
            info = _FALLBACK_FAULT_INFO["OR_014"]
            conf = min(0.55 + (vib_mag - 2.0) * 0.1, 0.95)
        else:
            class_id, class_label = 6, "Normal"
            info = _FALLBACK_FAULT_INFO["Normal"]
            conf = 0.97

        probs = [0.0] * 10
        probs[class_id] = conf
        # Spread remaining probability over neighbours
        if class_id > 0:
            probs[class_id - 1] = round((1 - conf) / 2, 4)
        if class_id < 9:
            probs[class_id + 1] = round((1 - conf) / 2, 4)

        return {
            "class_id":        class_id,
            "class_label":     class_label,
            "fault_location":  info["fault_location"],
            "severity_inches": info["severity_inches"],
            "confidence":      conf,
            "probabilities":   probs,
        }


# ── Global singleton ─────────────────────────────────────────────────
bearing_service = BearingService()
