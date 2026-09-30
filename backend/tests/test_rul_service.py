"""
Accuracy-First Phase 2 — RUL service lifecycle tests.

`test_rul_adapter.py` covers the piston->C-MAPSS translation; this file
covers the SERVICE built on top of it: the sliding window, the
INSUFFICIENT_DATA -> VALID transition, restart/recovery, and that the
already-computed split-conformal interval (rul_lower/rul_upper) is
sane and present alongside the point prediction.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.rul_service import rul_service
from app.services.rul_adapter import piston_to_cmapss

NOMINAL_READING = {
    "rpm": 4800.0, "throttle": 0.75, "altitude_m": 2400.0,
    "cht": 135.0, "egt": 650.0, "oil_pressure": 65.0, "oil_temp": 95.0,
    "fuel_flow": 10.0, "vibration_magnitude": 0.5, "deviation_score": 0.1,
}

DEGRADED_READING = {
    **NOMINAL_READING,
    "cht": 280.0, "deviation_score": 2.5, "vibration_magnitude": 8.0,
}


def _fresh_engine_id(name: str) -> str:
    """A unique key per test so windows never bleed across tests sharing
    the module-level `rul_service` singleton."""
    return f"test-rul-service-{name}"


def test_window_not_full_returns_none_not_a_fabricated_value():
    engine_id = _fresh_engine_id("insufficient")
    rul_service.reset_engine(engine_id)
    try:
        result = None
        for _ in range(rul_service.window_len - 1):  # one short of full
            result = rul_service.push_reading(engine_id, piston_to_cmapss(NOMINAL_READING))
        assert result is None
        assert 0 < rul_service.get_window_depth(engine_id) < rul_service.window_len
    finally:
        rul_service.reset_engine(engine_id)


def test_window_fill_transitions_to_a_real_prediction():
    engine_id = _fresh_engine_id("fills")
    rul_service.reset_engine(engine_id)
    try:
        result = None
        for _ in range(rul_service.window_len):
            result = rul_service.push_reading(engine_id, piston_to_cmapss(NOMINAL_READING))
        assert result is not None
        assert result["status"] in ("VALID", "MODEL_ERROR")
        assert 0.0 <= result["rul_cycles"] <= 125.0
        assert rul_service.get_window_depth(engine_id) == rul_service.window_len
    finally:
        rul_service.reset_engine(engine_id)


def test_prediction_interval_is_present_and_well_formed():
    engine_id = _fresh_engine_id("interval")
    rul_service.reset_engine(engine_id)
    try:
        result = None
        for _ in range(rul_service.window_len):
            result = rul_service.push_reading(engine_id, piston_to_cmapss(NOMINAL_READING))
        assert result["rul_lower"] <= result["rul_cycles"] <= result["rul_upper"]
        assert result["rul_lower"] >= 0.0
        assert result["rul_upper"] <= 125.0
    finally:
        rul_service.reset_engine(engine_id)


def test_sustained_degradation_reduces_rul_relative_to_nominal():
    """Monotonic-degradation scenario — a sustained fault should not
    produce a HIGHER RUL than sustained nominal operation."""
    nominal_id = _fresh_engine_id("nominal_cmp")
    degraded_id = _fresh_engine_id("degraded_cmp")
    rul_service.reset_engine(nominal_id)
    rul_service.reset_engine(degraded_id)
    try:
        nominal_result = None
        degraded_result = None
        for _ in range(rul_service.window_len):
            nominal_result = rul_service.push_reading(nominal_id, piston_to_cmapss(NOMINAL_READING))
            degraded_result = rul_service.push_reading(degraded_id, piston_to_cmapss(DEGRADED_READING))
        assert degraded_result["rul_cycles"] <= nominal_result["rul_cycles"]
        assert degraded_result["degradation_index"] >= nominal_result["degradation_index"]
    finally:
        rul_service.reset_engine(nominal_id)
        rul_service.reset_engine(degraded_id)


def test_restart_recovery_via_reset_engine():
    """reset_engine() (used by the Phase 6 replay path for window
    isolation) must fully clear state — a fresh window afterward must
    NOT immediately produce a prediction."""
    engine_id = _fresh_engine_id("recovery")
    rul_service.reset_engine(engine_id)
    try:
        for _ in range(rul_service.window_len):
            rul_service.push_reading(engine_id, piston_to_cmapss(NOMINAL_READING))
        assert rul_service.get_window_depth(engine_id) == rul_service.window_len

        rul_service.reset_engine(engine_id)
        assert rul_service.get_window_depth(engine_id) == 0

        result = rul_service.push_reading(engine_id, piston_to_cmapss(NOMINAL_READING))
        assert result is None  # one reading in a freshly-reset window is not enough
    finally:
        rul_service.reset_engine(engine_id)
