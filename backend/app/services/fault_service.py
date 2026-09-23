import os
import joblib
import json
import logging
import collections
import numpy as np
from typing import Optional, Dict

from app.services.fault_adapter import piston_to_uav_telemetry, extract_window_features

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
            # Fallback mock if models failed to load
            return {
                "class_id": 0,
                "fault_class": "No Failure",
                "confidence": 0.99,
                "probabilities": [0.99, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            }
            
        # Stage 1: Binary Detection
        is_fault = self._stage1_model.predict(features)[0]
        
        if is_fault == 0:
            # No Failure
            probs = self._stage1_model.predict_proba(features)[0]
            conf = float(probs[0])
            full_probs = [conf, 1-conf, 0.0, 0.0, 0.0, 0.0, 0.0]
            return {
                "class_id": 0,
                "fault_class": "No Failure",
                "confidence": conf,
                "probabilities": full_probs
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
            
        return {
            "class_id": class_id,
            "fault_class": FAULT_CLASSES[class_id],
            "confidence": conf,
            "probabilities": full_probs
        }

# Global singleton instance
fault_service = FaultService()
