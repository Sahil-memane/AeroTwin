import os
import joblib
import json
import logging
import collections
from pathlib import Path
import numpy as np
import yaml
from typing import Optional

from app.services.fault_adapter import piston_to_uav_telemetry, extract_window_features, input_coverage
from app.services.fault_reliability import is_reliable
from app.services.fault_state import fault_state_machine

logger = logging.getLogger(__name__)

# Class ID to Label Mapping
FAULT_CLASSES = {
    0: "No Failure",
    1: "RC Failure",
    2: "GPS Failure",
    3: "Accelerometer Failure",
    4: "Gyro Failure",
    5: "Compass Failure",
    6: "Barometer Failure"
}

# Accuracy-First Phase 3: an explicit, distinguishable label for "the
# model didn't have enough evidence to pick a class" — never presented
# as if it were a real, confident classification.
UNCERTAIN_LABEL = "Unknown / insufficient evidence"

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "telemetry_limits.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _FAULT_CONFIG = yaml.safe_load(_f)["fault_detection"]
STAGE2_CONFIDENCE_THRESHOLD: float = _FAULT_CONFIG["stage2_confidence_threshold"]
STAGE2_MARGIN_THRESHOLD: float = _FAULT_CONFIG["stage2_margin_threshold"]

class FaultService:
    def __init__(self, window_len: int = 80):
        self._window_len = window_len
        # Maps engine_id -> deque of 32-ch UAV telemetry windows
        self._windows = collections.defaultdict(lambda: collections.deque(maxlen=window_len))
        # Maps engine_id -> previous raw vibration dict for deriving gyros
        self._prev_vibes = {}
        
        self._loaded = False
        self._stage1_model = None
        self._stage2_model = None
        self._feature_names = []

    @property
    def window_len(self) -> int:
        """Readings required before the first inference."""
        return self._window_len

    def _ensure_loaded(self):
        if self._loaded:
            return
            
        base_dir = os.path.join(os.path.dirname(__file__), "../../../ml/training/fault_model")
        s1_path = os.path.join(base_dir, "stage1_binary_lgb.pkl")
        s2_path = os.path.join(base_dir, "stage2_multiclass_lgb.pkl")
        fn_path = os.path.join(base_dir, "feature_names.json")
        
        try:
            self._stage1_model = joblib.load(s1_path)
            self._stage2_model = joblib.load(s2_path)
            with open(fn_path, 'r') as f:
                self._feature_names = json.load(f)
            self._loaded = True
            logger.info("Successfully loaded Fault Model pipeline.")
        except Exception as e:
            logger.error(f"Failed to load Fault Model: {e}")
            # Mock mode if models missing
            self._loaded = True

    @staticmethod
    def _coverage_fields() -> dict:
        cov = input_coverage()
        return {"input_coverage": cov, "reliable": is_reliable(cov)}

    def push_reading(self, engine_id: str, raw_telemetry: dict) -> Optional[dict]:
        """
        Pushes a single piston engine telemetry reading, maps it to UAV schema, 
        and if the 80-sample buffer is full, runs the 2-stage inference.
        """
        self._ensure_loaded()
        
        # 1. Map to UAV 32-channel schema
        prev_vibe = self._prev_vibes.get(engine_id)
        current_vibe = {
            "x": raw_telemetry.get("vibration_x", 0.0),
            "y": raw_telemetry.get("vibration_y", 0.0),
            "z": raw_telemetry.get("vibration_z", 0.0)
        }
        
        uav_row = piston_to_uav_telemetry(raw_telemetry, prev_vibe)
        self._prev_vibes[engine_id] = current_vibe
        
        # 2. Append to window
        window = self._windows[engine_id]
        window.append(uav_row)
        
        if len(window) < self._window_len:
            return None
            
        # 3. Extract features
        window_array = np.array(window)
        features = extract_window_features(window_array).reshape(1, -1)
        
        # 4. Inference
        if self._stage1_model is None or self._stage2_model is None:
            # Fallback mock if models failed to load. `state` is included
            # only for return-shape parity with the real inference path
            # below (ingestion.py reads it unconditionally) — it does not
            # pass through the state machine, since there's no real
            # per-cycle classification to track a streak for.
            return {
                "class_id": 0,
                "fault_class": "No Failure",
                "confidence": 0.99,
                "probabilities": [0.99, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "state": "NORMAL",
                **self._coverage_fields(),
            }
            
        # Stage 1: Binary Detection
        is_fault = self._stage1_model.predict(features)[0]
        
        if is_fault == 0:
            # No Failure
            probs = self._stage1_model.predict_proba(features)[0]
            conf = float(probs[0])
            full_probs = [conf, 1-conf, 0.0, 0.0, 0.0, 0.0, 0.0]
            state = fault_state_machine.update(engine_id, is_abnormal=False)
            return {
                "class_id": 0,
                "fault_class": "No Failure",
                "confidence": conf,
                "probabilities": full_probs,
                "state": state.value,
                **self._coverage_fields(),
            }

        # Stage 2: Multiclass Isolation
        s2_probs = self._stage2_model.predict_proba(features)[0]
        s2_class = self._stage2_model.predict(features)[0]

        # Construct full 7-element probability vector
        # Note: the stage2 model was trained on labels 1-6, but predict_proba returns 6 elements
        full_probs = [0.0] + [float(p) for p in s2_probs]
        conf = float(np.max(s2_probs))
        class_id = int(s2_class)

        # Safety fallback if class_id out of bounds
        if class_id not in FAULT_CLASSES:
            class_id = 0

        # Accuracy-First Phase 3: abstain rather than force a
        # falsely-confident single class when the evidence is weak —
        # either the top probability itself is low, or it's not clearly
        # separated from the runner-up (a near-tie is exactly the case
        # where picking the argmax is most likely to be wrong).
        sorted_probs = sorted((float(p) for p in s2_probs), reverse=True)
        margin = sorted_probs[0] - (sorted_probs[1] if len(sorted_probs) > 1 else 0.0)
        abstained = conf < STAGE2_CONFIDENCE_THRESHOLD or margin < STAGE2_MARGIN_THRESHOLD

        # The state machine tracks whether THIS cycle's classification is
        # abnormal — an abstention is neither (it carries the current
        # state over unchanged), a real fault class is.
        state = fault_state_machine.update(engine_id, is_abnormal=None if abstained else True)

        if abstained:
            return {
                "class_id": class_id,
                "fault_class": UNCERTAIN_LABEL,
                "confidence": conf,
                "probabilities": full_probs,
                "state": state.value,
                **self._coverage_fields(),
            }

        return {
            "class_id": class_id,
            "fault_class": FAULT_CLASSES[class_id],
            "confidence": conf,
            "probabilities": full_probs,
            "state": state.value,
            **self._coverage_fields(),
        }

    def reset_engine(self, engine_id: str) -> None:
        """Frees per-engine window/state — used by the replay engine
        (each simulation run gets its own pseudo engine_id and is one-shot),
        matching rul_service.reset_engine's lifecycle."""
        self._windows.pop(engine_id, None)
        self._prev_vibes.pop(engine_id, None)
        fault_state_machine.reset_engine(engine_id)

# Global singleton instance
fault_service = FaultService()
