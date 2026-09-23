"""
RUL Inference Service — Remaining Useful Life prediction pipeline.

Implements the complete inference flow:
  1. Accept a piston-engine telemetry reading
  2. Translate it to C-MAPSS format via the Translating Adapter
  3. Scale using the trained condition + regime scalers
  4. Maintain a per-engine sliding window (30 cycles)
  5. Extract 216 statistical features from the window
  6. Run XGBoost inference
  7. Return RUL prediction with confidence interval

The sliding window is stored in-memory (dict keyed by engine_id).
In production this would use Redis; for the hackathon demo this is
sufficient and avoids an external dependency on the hot path.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Paths to model artifacts ─────────────────────────────────────────
_MODEL_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "ml", "training",
    "rul_model", "CMaps", "saved_models",
))


class RULInferenceService:
    """
    Stateful per-engine RUL prediction service.

    Lazily loads model artifacts on first call to avoid slowing
    FastAPI startup when the model files may not be present.
    """

    def __init__(self, model_dir: str = _MODEL_DIR):
        self._model_dir = model_dir
        self._loaded = False

        # Per-engine sliding windows: engine_id → list of C-MAPSS rows
        self._windows: Dict[str, List[np.ndarray]] = defaultdict(list)

        # Model artifacts (populated on first load)
        self._xgb_model = None
        self._condition_scaler = None
        self._regime_kmeans = None
        self._regime_scalers = None
        self._config: dict = {}
        self._window_len: int = 30
        self._rul_cap: int = 125
        self._conformal_q: float = 22.82
        self._feature_cols: List[str] = []
        self._setting_cols: List[str] = []
        self._keep_sensors: List[str] = []

    # ── Lazy loading ─────────────────────────────────────────────────

    def _load(self):
        """Load all model artifacts from disk."""
        import joblib
        
        try:
            import xgboost as xgb
            self._has_xgboost = True
        except ImportError:
            logger.warning("XGBoost not installed. RUL Inference will run in MOCK mode.")
            self._has_xgboost = False

        config_path = os.path.join(self._model_dir, "inference_config.json")
        with open(config_path, "r") as f:
            self._config = json.load(f)

        self._window_len = self._config.get("window_len", 30)
        self._rul_cap = self._config.get("rul_cap", 125)
        self._conformal_q = self._config.get("conformal_q", 22.82)
        self._feature_cols = self._config["feature_cols"]
        self._setting_cols = self._config["setting_cols"]
        self._keep_sensors = self._config["keep_sensors"]

        self._condition_scaler = joblib.load(
            os.path.join(self._model_dir, "condition_scaler.joblib")
        )
        self._regime_kmeans = joblib.load(
            os.path.join(self._model_dir, "regime_kmeans.joblib")
        )
        self._regime_scalers = joblib.load(
            os.path.join(self._model_dir, "regime_scalers.joblib")
        )

        if self._has_xgboost:
            self._xgb_model = xgb.Booster()
            self._xgb_model.load_model(
                os.path.join(self._model_dir, "xgb_rul_model.json")
            )
        else:
            self._xgb_model = None

        self._loaded = True
        logger.info("RUL model artifacts loaded from %s (Mock Mode: %s)", self._model_dir, not self._has_xgboost)

    def _ensure_loaded(self):
        if not self._loaded:
            self._load()

    # ── Feature engineering ──────────────────────────────────────────

    def _extract_window_features(self, window: np.ndarray) -> np.ndarray:
        """
        Extract 9 statistical features per column from the sliding window.

        For each of the 24 columns, compute:
          mean, std, slope, last5_mean, last, first_last, max, min, range

        Returns a flat array of 24 × 9 = 216 features.
        """
        n_cols = window.shape[1]
        features = []

        for col_idx in range(n_cols):
            col_data = window[:, col_idx]
            n = len(col_data)

            col_mean = np.mean(col_data)
            col_std = np.std(col_data)

            # Slope via simple linear regression
            if n > 1:
                x = np.arange(n, dtype=np.float64)
                slope = (np.sum(x * col_data) - n * np.mean(x) * col_mean) / \
                        max(np.sum(x ** 2) - n * np.mean(x) ** 2, 1e-9)
            else:
                slope = 0.0

            last5_mean = np.mean(col_data[-5:]) if n >= 5 else col_mean
            last_val = col_data[-1]
            first_last = col_data[-1] - col_data[0]
            col_max = np.max(col_data)
            col_min = np.min(col_data)
            col_range = col_max - col_min

            features.extend([
                col_mean, col_std, slope, last5_mean,
                last_val, first_last, col_max, col_min, col_range,
            ])

        return np.array(features, dtype=np.float64)

    # ── Preprocessing pipeline ───────────────────────────────────────

    def _preprocess_row(self, cmapss_row: dict) -> np.ndarray:
        """
        Apply condition scaling and regime-specific sensor scaling
        to a single C-MAPSS row, exactly as done during training.

        Returns a 24-element array (3 settings + 21 sensors, all scaled).
        """
        # Extract settings and sensors in order
        settings = np.array(
            [cmapss_row[c] for c in self._setting_cols], dtype=np.float64
        ).reshape(1, -1)

        sensors = np.array(
            [cmapss_row[c] for c in self._keep_sensors], dtype=np.float64
        ).reshape(1, -1)

        # Scale operating conditions and determine regime
        settings_scaled = self._condition_scaler.transform(settings)
        regime = int(self._regime_kmeans.predict(settings_scaled)[0])

        # Apply regime-specific sensor scaling
        regime_scaler = self._regime_scalers[regime]
        sensors_scaled = regime_scaler.transform(sensors)

        # Concatenate: [settings_scaled | sensors_scaled]
        return np.concatenate([settings_scaled[0], sensors_scaled[0]])

    # ── Public API ───────────────────────────────────────────────────

    def push_reading(
        self, engine_id: str, cmapss_row: dict
    ) -> Optional[dict]:
        """
        Push a C-MAPSS-format reading for an engine and return a RUL
        prediction if the window is full (≥ window_len cycles).

        Parameters
        ----------
        engine_id : str
            Engine UUID.
        cmapss_row : dict
            24-column C-MAPSS dict (from ``rul_adapter.piston_to_cmapss``).

        Returns
        -------
        dict | None
            ``None`` if the window is not yet full.
            Otherwise: ``{"rul_cycles": float, "rul_lower": float,
                          "rul_upper": float, "degradation_index": float}``
        """
        self._ensure_loaded()

        # Preprocess and append to sliding window
        scaled_row = self._preprocess_row(cmapss_row)
        window = self._windows[engine_id]
        window.append(scaled_row)

        # Trim to window_len (keep only the latest N readings)
        if len(window) > self._window_len:
            self._windows[engine_id] = window[-self._window_len:]
            window = self._windows[engine_id]

        # Not enough data yet
        if len(window) < self._window_len:
            logger.debug(
                "Engine %s: %d/%d cycles buffered",
                engine_id, len(window), self._window_len,
            )
            return None

        # ── Extract features and predict ─────────────────────────────
        if self._has_xgboost:
            import xgboost as xgb
            window_array = np.array(window)  # shape: (window_len, 24)
            features = self._extract_window_features(window_array)
            dmat = xgb.DMatrix(features.reshape(1, -1))
            raw_pred = float(self._xgb_model.predict(dmat)[0])
        else:
            # Mock prediction logic (e.g. returns 100 as a placeholder)
            logger.warning("Mocking RUL prediction because XGBoost is missing.")
            raw_pred = 100.0

        # Clamp to [0, rul_cap]
        rul_cycles = max(0.0, min(float(self._rul_cap), raw_pred))

        # Conformal prediction interval
        rul_lower = max(0.0, rul_cycles - self._conformal_q)
        rul_upper = min(float(self._rul_cap), rul_cycles + self._conformal_q)

        # Degradation index: 0.0 = healthy, 1.0 = imminent failure
        degradation_index = max(0.0, min(1.0, 1.0 - (rul_cycles / self._rul_cap)))

        return {
            "rul_cycles": round(rul_cycles, 2),
            "rul_lower": round(rul_lower, 2),
            "rul_upper": round(rul_upper, 2),
            "degradation_index": round(degradation_index, 4),
        }

    def get_window_depth(self, engine_id: str) -> int:
        """How many cycles are currently buffered for this engine."""
        return len(self._windows.get(engine_id, []))

    def reset_engine(self, engine_id: str):
        """Clear the sliding window for an engine (e.g., new mission)."""
        self._windows.pop(engine_id, None)


# Module-level singleton
rul_service = RULInferenceService()