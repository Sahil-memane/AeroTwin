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
    PARAMETER_TOLERANCES,
    compute_expected_telemetry,
    compute_physics_deviation,
    EngineSpecs,
    DEFAULT_SPECS,
)

__all__ = [
    "OttoCycleSolver",
    "ExpectedTelemetry",
    "PhysicsDeviation",
    "PARAMETER_TOLERANCES",
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
    # Pass the WHOLE reading through as `actual_telemetry` — not a
    # hand-copied subset — so compute_physics_deviation's own
    # operating-conditions inference (`actual_telemetry.get("throttle",
    # ...)`, `.get("altitude_m", ...)`, etc.) sees the reading's REAL
    # throttle/altitude_m/ambient_temp_c/airspeed_mps when present,
    # instead of silently falling back to an RPM-estimated throttle.
    # [Fixed here, Accuracy-First Phase 4: this wrapper previously built
    # a narrow `actual` dict containing only the 6 measured channels,
    # which discarded the reading's own throttle/altitude_m even when
    # they existed — confirmed live, this made every non-explicit-
    # throttle call estimate throttle from RPM rather than use the real
    # telemetry field the simulator already emits.] Extra keys (ts,
    # engine_id, …) are harmless — compute_physics_deviation only reads
    # the specific fields it needs.
    actual = dict(reading)
    if throttle is not None:
        actual["throttle"] = throttle
    if altitude_m:
        actual["altitude_m"] = altitude_m
    if ambient_temp_c is not None:
        actual["ambient_temp_c"] = ambient_temp_c

    return compute_physics_deviation(actual)
