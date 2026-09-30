"""
Edge-local RUL inference — same pipeline as
`backend/app/services/rul_service.py` (condition scaling -> regime
assignment -> per-regime sensor scaling -> 30-cycle sliding window ->
216 statistical features -> XGBoost regression), but running the
ONNX-exported booster via `onnxruntime` and re-implementing the
StandardScaler/KMeans preprocessing as plain numpy from the parameters
`ml/export_onnx.py` dumped to `rul_preprocessing.json` — see that
script's docstring for why the preprocessing isn't itself an ONNX graph.
`rul_adapter.piston_to_cmapss` (a pure, dependency-light function) is
imported directly from the backend rather than duplicated.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional

import numpy as np
import onnxruntime as ort

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BACKEND_ROOT = os.path.join(_REPO_ROOT, "backend")
for p in (_REPO_ROOT, _BACKEND_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.rul_adapter import piston_to_cmapss  # noqa: E402

_MODELS_DIR = os.path.join(_REPO_ROOT, "ml", "models")


def _standard_scale(x: np.ndarray, mean: List[float], scale: List[float]) -> np.ndarray:
    return (x - np.array(mean)) / np.array(scale)


class EdgeRULRunner:
    def __init__(self, models_dir: str = _MODELS_DIR):
        with open(os.path.join(models_dir, "rul_preprocessing.json")) as f:
            pp = json.load(f)

        self._window_len: int = pp["window_len"]
        self._rul_cap: int = pp["rul_cap"]
        self._conformal_q: float = pp["conformal_q"]
        self._setting_cols: List[str] = pp["setting_cols"]
        self._keep_sensors: List[str] = pp["keep_sensors"]
        self._condition_scaler = pp["condition_scaler"]
        self._cluster_centers = np.array(pp["regime_kmeans"]["cluster_centers"])
        self._regime_scalers = pp["regime_scalers"]
        self._trained_feature_names = pp["trained_feature_names"]

        self._session = ort.InferenceSession(os.path.join(models_dir, "rul_xgb.onnx"))
        self._windows: Dict[str, list] = defaultdict(list)

    def _preprocess_row(self, cmapss_row: dict) -> np.ndarray:
        settings = np.array([cmapss_row[c] for c in self._setting_cols], dtype=np.float64)
        sensors = np.array([cmapss_row[c] for c in self._keep_sensors], dtype=np.float64)

        settings_scaled = _standard_scale(
            settings, self._condition_scaler["mean"], self._condition_scaler["scale"]
        )

        # Nearest-centroid lookup — exactly what KMeans.predict() does at
        # inference time (no re-fitting, just a distance argmin).
        dists = np.linalg.norm(self._cluster_centers - settings_scaled, axis=1)
        regime = int(np.argmin(dists))

        regime_scaler = self._regime_scalers[str(regime)]
        sensors_scaled = _standard_scale(sensors, regime_scaler["mean"], regime_scaler["scale"])

        return np.concatenate([settings_scaled, sensors_scaled])

    @staticmethod
    def _extract_window_features(window: np.ndarray) -> np.ndarray:
        """Mirrors `RULInferenceService._extract_window_features` exactly
        (same stat order the trained booster expects) — see that
        docstring for the field order rationale."""
        n_cols = window.shape[1]
        features = []
        for col_idx in range(n_cols):
            col_data = window[:, col_idx]
            n = len(col_data)
            col_mean = np.mean(col_data)
            col_std = np.std(col_data)
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
            features.extend([col_mean, col_std, last_val, col_min, col_max,
                              slope, col_range, first_last, last5_mean])
        return np.array(features, dtype=np.float64)

    def push_reading(self, engine_id: str, raw_telemetry: dict) -> Optional[dict]:
        cmapss_row = piston_to_cmapss(raw_telemetry)
        scaled_row = self._preprocess_row(cmapss_row)

        window = self._windows[engine_id]
        window.append(scaled_row)
        if len(window) > self._window_len:
            self._windows[engine_id] = window[-self._window_len:]
            window = self._windows[engine_id]
        if len(window) < self._window_len:
            return None

        features = self._extract_window_features(np.array(window)).reshape(1, -1).astype(np.float32)
        raw_pred = float(self._session.run(None, {"input": features})[0].ravel()[0])

        rul_cycles = max(0.0, min(float(self._rul_cap), raw_pred))
        rul_lower = max(0.0, rul_cycles - self._conformal_q)
        rul_upper = min(float(self._rul_cap), rul_cycles + self._conformal_q)
        degradation_index = max(0.0, min(1.0, 1.0 - (rul_cycles / self._rul_cap)))

        return {
            "rul_cycles": round(rul_cycles, 2),
            "rul_lower": round(rul_lower, 2),
            "rul_upper": round(rul_upper, 2),
            "degradation_index": round(degradation_index, 4),
            # Always VALID here — unlike the backend's xgboost-missing
            # mock fallback, a missing/broken ONNX file is a load-time
            # crash for this runner, not a degraded runtime mode.
            "status": "VALID",
        }
