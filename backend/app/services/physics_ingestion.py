"""
Physics-consistency computation for live telemetry — Accuracy-First
Phase 4 (pulled forward from the source document's Tier 2). Before this,
`deviation_score` — RUL's #1-importance feature (27.4%, per
rul_adapter.py's own docstring) — was only ever supplied by the demo
simulator itself; any other telemetry source silently fell back to 0.0
("nominal") inside rul_adapter.piston_to_cmapss. This computes a real,
server-side deviation from the already-built Otto-cycle physics model
for every live reading, regardless of source.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import yaml

from app.services.physics_model import compute_deviation_from_reading, PARAMETER_TOLERANCES

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "telemetry_limits.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _PC_CONFIG = yaml.safe_load(_f)["physics_consistency"]

ELEVATED_MULTIPLIER: float = _PC_CONFIG["elevated_multiplier"]
REVIEW_MULTIPLIER: float = _PC_CONFIG["review_multiplier"]
ANOMALY_MULTIPLIER: float = _PC_CONFIG["anomaly_multiplier"]

METHOD = "documented_baseline_v1"

# (parameter name, PhysicsDeviation attribute for the delta, PhysicsDeviation.expected attribute)
_PARAMETERS = [
    ("cht", "delta_cht", "cht"),
    ("egt", "delta_egt", "egt"),
    ("oil_pressure", "delta_oil_pressure", "oil_pressure"),
    ("oil_temp", "delta_oil_temp", "oil_temp"),
    ("fuel_flow", "delta_fuel_flow", "fuel_flow_gph"),
]


@dataclass
class ParameterConsistency:
    parameter: str
    expected: float
    measured: float
    residual: float
    status: str
    method: str = METHOD


def _status_for(residual: float, tolerance: float) -> str:
    magnitude = abs(residual) / tolerance
    if magnitude > ANOMALY_MULTIPLIER:
        return "ANOMALY"
    if magnitude > REVIEW_MULTIPLIER:
        return "REVIEW"
    if magnitude > ELEVATED_MULTIPLIER:
        return "ELEVATED"
    return "CONSISTENT"


def compute_consistency(reading: dict) -> Tuple[float, List[ParameterConsistency]]:
    """
    `reading`: a raw telemetry dict — must contain rpm/cht/egt/
    oil_pressure/oil_temp/fuel_flow, may contain throttle/altitude_m
    (used if present, estimated otherwise — see
    physics_model.compute_deviation_from_reading).

    Returns `(deviation_score, [ParameterConsistency, ...])` — the
    composite score (fed into rul_adapter.piston_to_cmapss in place of
    the previously client-trusted field) and one per-channel result for
    each of the 5 parameters the physics model covers. Never fabricated;
    every value here traces back to a real Otto-cycle solver output or a
    real measured telemetry field.
    """
    deviation = compute_deviation_from_reading(reading)
    results = []
    for name, delta_attr, expected_attr in _PARAMETERS:
        residual = getattr(deviation, delta_attr)
        expected = getattr(deviation.expected, expected_attr)
        results.append(ParameterConsistency(
            parameter=name,
            expected=round(expected, 2),
            measured=round(reading[name], 2),
            residual=round(residual, 2),
            status=_status_for(residual, PARAMETER_TOLERANCES[name]),
        ))
    return deviation.deviation_score, results
