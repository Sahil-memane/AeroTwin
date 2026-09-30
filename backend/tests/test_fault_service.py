"""
Fault Detection Reliability — Accuracy-First Phase 3. Verifies
`FaultService.push_reading`'s stage-2 abstention logic and its
integration with the temporal-consistency state machine, using fake
stage1/stage2 models (no real .pkl load, no GPU/CPU inference cost) so
each probability vector under test is exact and controlled rather than
whatever the real trained model happens to produce for synthetic input.
"""
import numpy as np
import pytest

from app.services.fault_service import FaultService, UNCERTAIN_LABEL


class _FakeStage1:
    """Always reports a fault (so stage 2 always runs) unless told otherwise."""

    def __init__(self, is_fault: int = 1):
        self._is_fault = is_fault

    def predict(self, features):
        return np.array([self._is_fault])

    def predict_proba(self, features):
        # [P(no fault), P(fault)] — only index 0 is read by the "no fault" branch.
        return np.array([[1.0 - self._is_fault, float(self._is_fault)]])


class _FakeStage2:
    """Returns a fixed 6-element probability vector (classes 1-6) and its argmax label."""

    def __init__(self, probs: list[float]):
        self._probs = np.array(probs)

    def predict_proba(self, features):
        return np.array([self._probs])

    def predict(self, features):
        return np.array([int(np.argmax(self._probs)) + 1])  # stage2 labels are 1-6


def _raw_reading(i: int = 0) -> dict:
    return {
        "rpm": 2500.0 + i, "cht": 90.0, "egt": 700.0, "oil_pressure": 55.0,
        "oil_temp": 95.0, "fuel_flow": 12.0,
        "vibration_x": 0.1, "vibration_y": 0.05, "vibration_z": 9.8,
    }


def _fill_window_and_push(svc: FaultService, engine_id: str, n_extra: int = 0):
    """Pushes window_len-1 filler readings (returns None each time, window
    not yet full) then one final reading and returns ITS result."""
    result = None
    for i in range(svc._window_len + n_extra):
        result = svc.push_reading(engine_id, _raw_reading(i))
    return result


def make_service(stage2_probs: list[float], is_fault: int = 1) -> FaultService:
    svc = FaultService(window_len=10)  # small window — faster tests
    svc._loaded = True
    svc._stage1_model = _FakeStage1(is_fault=is_fault)
    svc._stage2_model = _FakeStage2(stage2_probs)
    return svc


# Accuracy-First Phase 3's fault state machine is a module-level
# singleton (app.services.fault_state.fault_state_machine) shared by
# every FaultService instance — exactly like production, where there's
# only ever one. Each test therefore uses its own unique engine_id so
# tests can't leak state into each other regardless of execution order.


def test_confident_clear_margin_is_not_abstained():
    # top1=0.90 at index 4 (class_id 5, "Compass Failure"), next-best
    # 0.02 — well clear of both the 0.45 confidence floor and the 0.15
    # margin floor.
    svc = make_service([0.02, 0.02, 0.02, 0.02, 0.90, 0.02])
    result = _fill_window_and_push(svc, "test-confident-margin")
    assert result["fault_class"] == "Compass Failure"
    assert result["state"] == "ANOMALY_DETECTED"  # first abnormal reading in this engine's history


def test_low_top_probability_abstains():
    # Near-uniform across 6 classes — no class reaches the 0.45 confidence floor.
    svc = make_service([1 / 6] * 6)
    result = _fill_window_and_push(svc, "test-low-confidence")
    assert result["fault_class"] == UNCERTAIN_LABEL
    assert result["confidence"] == pytest.approx(1 / 6)


def test_high_confidence_but_thin_margin_abstains():
    # Top1=0.50 clears the confidence floor, but top2=0.40 leaves only a
    # 0.10 margin — below the 0.15 margin floor, so this is a near-tie.
    svc = make_service([0.05, 0.50, 0.40, 0.02, 0.02, 0.01])
    result = _fill_window_and_push(svc, "test-thin-margin")
    assert result["fault_class"] == UNCERTAIN_LABEL


def test_abstention_does_not_advance_or_reset_the_fault_streak():
    # Uses the real configured thresholds (telemetry_limits.yaml:
    # fault_detection.state_machine) — anomaly_to_suspect_streak: 3.
    engine_id = "test-abstention-streak"
    confident_probs = [0.02, 0.02, 0.02, 0.02, 0.90, 0.02]  # "Compass Failure"
    svc = make_service(confident_probs)

    r1 = _fill_window_and_push(svc, engine_id)  # streak=1
    assert r1["state"] == "ANOMALY_DETECTED"

    # Swap in a near-uniform (abstaining) stage2 for exactly one reading —
    # this must NOT count toward the streak in either direction.
    svc._stage2_model = _FakeStage2([1 / 6] * 6)
    r2 = svc.push_reading(engine_id, _raw_reading(999))
    assert r2["fault_class"] == UNCERTAIN_LABEL
    assert r2["state"] == "ANOMALY_DETECTED"  # unchanged, not reset to NORMAL

    # Swap back to confident — the streak (1) should have been preserved
    # across the abstention. Two more real abnormal readings complete
    # the streak-of-3 needed to reach FAULT_SUSPECTED.
    svc._stage2_model = _FakeStage2(confident_probs)
    r3 = svc.push_reading(engine_id, _raw_reading(1000))  # streak=2
    assert r3["state"] == "ANOMALY_DETECTED"
    r4 = svc.push_reading(engine_id, _raw_reading(1001))  # streak=3
    assert r4["state"] == "FAULT_SUSPECTED"


def test_no_failure_branch_reports_normal_state():
    svc = make_service(stage2_probs=[0.0] * 6, is_fault=0)
    result = _fill_window_and_push(svc, "test-no-failure")
    assert result["fault_class"] == "No Failure"
    assert result["state"] == "NORMAL"


def test_reset_engine_clears_window_and_state():
    engine_id = "test-reset-engine"
    svc = make_service([0.02, 0.02, 0.02, 0.90, 0.02, 0.02])
    _fill_window_and_push(svc, engine_id)
    assert len(svc._windows[engine_id]) == svc._window_len

    svc.reset_engine(engine_id)
    assert len(svc._windows[engine_id]) == 0
    # State machine forgot the streak too — a fresh engine_id starts at
    # ANOMALY_DETECTED again on the very next abnormal reading, not
    # wherever the old streak had reached.
    result = _fill_window_and_push(svc, engine_id)
    assert result["state"] == "ANOMALY_DETECTED"


def test_window_not_full_returns_none():
    svc = make_service([0.02, 0.02, 0.02, 0.90, 0.02, 0.02])
    result = svc.push_reading("test-window-not-full", _raw_reading())
    assert result is None
