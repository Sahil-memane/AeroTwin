"""
Runs a sequence of telemetry readings — either replayed from stored
`telemetry_readings` (mission replay) or synthetically generated
(what-if) — through the exact same 4 ML model services + Health Fusion
that live MQTT ingestion uses, WITHOUT writing to the live prediction
tables (a replay must never collide with, or be mistaken for, real
production predictions sharing the same (engine_id, ts) primary key,
and a what-if run has no real `ts` to begin with).

Per-engine model state (the RUL/Fault sliding windows) is keyed by a
replay-namespaced pseudo engine_id so a replay never shares or corrupts
a live engine's real inference window.
"""
import math
import sys
import os
from typing import Optional

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services.rul_adapter import piston_to_cmapss  # noqa: E402
from app.services.rul_service import rul_service  # noqa: E402
from app.services.fault_service import fault_service  # noqa: E402
from app.services.aux_service import aux_service  # noqa: E402
from app.services.bearing_service import bearing_service  # noqa: E402
from app.services.health_fusion import compute_health_score  # noqa: E402
from app.services.physics_ingestion import compute_consistency  # noqa: E402


def _vibration_magnitude(reading: dict) -> Optional[float]:
    vx, vy, vz = reading.get("vibration_x"), reading.get("vibration_y"), reading.get("vibration_z")
    if vx is None or vy is None or vz is None:
        return None
    return round(math.sqrt(vx**2 + vy**2 + vz**2), 3)


class _FusionInputs:
    """Lightweight stand-ins matching the attributes `compute_health_score` reads —
    it only needs plain attribute access, not real ORM model instances."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def run_sequence(readings: list[dict], simulation_id: str) -> list[dict]:
    """
    `readings`: ordered list of telemetry dicts (rpm/cht/egt/oil_pressure/
    oil_temp/fuel_flow/vibration_x/y/z, plus optional ts/throttle/altitude_m).
    Returns one result frame per reading: {ts, telemetry, rul, fault, bearing, aux, health_score}.
    """
    window_key = f"replay::{simulation_id}"  # isolates model sliding-window state from live engines
    results = []

    for i, reading in enumerate(readings):
        data = dict(reading)
        data.setdefault("vibration_magnitude", _vibration_magnitude(reading))
        # Same server-side physics deviation live ingestion computes
        # (ingestion.py) — RUL's #1-importance feature. Previously omitted
        # here, so replay/what-if RUL silently saw deviation_score=0.
        try:
            data["deviation_score"] = compute_consistency(data)[0]
        except Exception:
            pass

        rul_result = None
        try:
            cmapss_row = piston_to_cmapss(data)
            rul_result = rul_service.push_reading(window_key, cmapss_row)
        except Exception:
            rul_result = None

        fault_result = fault_service.push_reading(window_key, data)
        aux_result = aux_service.push_reading(window_key, data)
        bearing_result = bearing_service.push_reading(window_key, data)

        rul_obj = _FusionInputs(**rul_result) if rul_result else None
        fault_obj = (
            _FusionInputs(
                fault_class=fault_result["fault_class"],
                confidence=fault_result["confidence"],
                state=fault_result.get("state"),
                input_coverage=fault_result.get("input_coverage"),
            )
            if fault_result
            else None
        )
        bearing_obj = (
            _FusionInputs(
                class_label=bearing_result["class_label"],
                fault_location=bearing_result["fault_location"],
                severity_inches=bearing_result["severity_inches"],
            )
            if bearing_result
            else None
        )
        aux_obj = (
            _FusionInputs(
                failure_probability_pct=aux_result["failure_probability_pct"],
                primary_failure_cause=aux_result.get("primary_failure_cause"),
                detected_failure_types=aux_result.get("detected_failure_types") or [],
            )
            if aux_result
            else None
        )

        health = compute_health_score(rul_obj, fault_obj, bearing_obj, aux_obj)

        results.append({
            "step": i,
            "ts": reading.get("ts"),
            "telemetry": {
                "rpm": reading.get("rpm"),
                "cht": reading.get("cht"),
                "egt": reading.get("egt"),
                "oil_pressure": reading.get("oil_pressure"),
                "oil_temp": reading.get("oil_temp"),
                "fuel_flow": reading.get("fuel_flow"),
            },
            "rul": rul_result,
            "fault": fault_result,
            "bearing": bearing_result,
            "aux": aux_result,
            "health_score": {
                "combined_score": health.combined_score,
                "contributing_factors": health.contributing_factors,
            },
        })

    # Replay windows are one-shot — free the memory rather than leaking
    # a per-run dict entry into these process-lifetime services forever.
    rul_service.reset_engine(window_key)
    fault_service.reset_engine(window_key)

    return results
