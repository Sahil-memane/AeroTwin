"""
Backend-side wrapper for the AeroTwin physics model.

Exposes the physics model's pure functions for use by:
  - The ingestion pipeline (computing deviation features in real time)
  - REST API endpoints (serving expected telemetry & deviation on demand)
  - The health fusion engine (consuming deviation_score as a fusion input)

This module re-exports from ``ml.training.physics_model`` so that the
backend codebase can import from a single canonical location without
needing to know the ML package structure.
"""

from __future__ import annotations

import sys
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Ensure the ml/ package is importable from the backend ─────────────
# In production the physics_model would be installed as a proper package;
# during development the ml/ directory sits adjacent to backend/.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ml_path = os.path.join(_project_root, "ml")
if _ml_path not in sys.path:
    sys.path.insert(0, _ml_path)

from training.physics_model import (  # noqa: E402
    OttoCycleSolver,
    ExpectedTelemetry,
    PhysicsDeviation,
    compute_expected_telemetry,
    compute_physics_deviation,
    EngineSpecs,
    DEFAULT_SPECS,
)

__all__ = [
    "OttoCycleSolver",
    "ExpectedTelemetry",
    "PhysicsDeviation",
    "compute_expected_telemetry",
    "compute_physics_deviation",
    "compute_deviation_from_reading",
    "EngineSpecs",
    "DEFAULT_SPECS",
]


def compute_deviation_from_reading(
    reading: dict,
    throttle: Optional[float] = None,
    altitude_m: float = 0.0,
    ambient_temp_c: Optional[float] = None,
) -> PhysicsDeviation:
    """
    Convenience function for the ingestion pipeline.

    Accepts a raw telemetry reading dict (as stored in
    ``telemetry_readings``) and returns the physics deviation.

    Parameters
    ----------
    reading : dict
        Must contain ``rpm``, ``cht``, ``egt``, ``oil_pressure``,
        ``oil_temp``, ``fuel_flow``.
    throttle : float | None
        If known; otherwise estimated from RPM.
    altitude_m : float
        Flight altitude [m] (default sea level).
    ambient_temp_c : float | None
        Ambient temperature override [°C].

    Returns
    -------
    PhysicsDeviation
    """
    actual = {
        "rpm": reading["rpm"],
        "cht": reading["cht"],
        "egt": reading["egt"],
        "oil_pressure": reading["oil_pressure"],
        "oil_temp": reading["oil_temp"],
        "fuel_flow": reading["fuel_flow"],
    }

    ops: dict = {"rpm": reading["rpm"]}
    if throttle is not None:
        ops["throttle"] = throttle
    ops["altitude_m"] = altitude_m
    if ambient_temp_c is not None:
        ops["ambient_temp_c"] = ambient_temp_c

    return compute_physics_deviation(actual, ops if throttle is not None else None)
