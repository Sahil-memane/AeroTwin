"""
Fault Detection temporal-consistency state machine — Accuracy-First
Phase 3. Uses a private instance with small, explicit thresholds
(rather than the real config's production defaults) so each transition
boundary is exercised exactly, not inferred from the shipped values.
"""
from app.services.fault_state import FaultState, FaultStateMachine


def make_sm():
    return FaultStateMachine(anomaly_to_suspect=3, suspect_to_confirm=5, confirmed_to_recovered=3)


def feed(sm, engine_id, sequence):
    """sequence: list of True (abnormal) / False (normal) / None (abstain)."""
    state = None
    for is_abnormal in sequence:
        state = sm.update(engine_id, is_abnormal)
    return state


def test_starts_normal():
    sm = make_sm()
    assert sm.update("e1", is_abnormal=False) == FaultState.NORMAL


def test_single_abnormal_reading_is_only_anomaly_detected_not_confirmed():
    sm = make_sm()
    state = sm.update("e1", is_abnormal=True)
    assert state == FaultState.ANOMALY_DETECTED


def test_full_escalation_to_suspected_then_confirmed():
    sm = make_sm()
    # streak 1 -> ANOMALY_DETECTED
    assert feed(sm, "e1", [True]) == FaultState.ANOMALY_DETECTED
    # streak 2 -> still ANOMALY_DETECTED (threshold is 3)
    assert feed(sm, "e1", [True]) == FaultState.ANOMALY_DETECTED
    # streak 3 -> FAULT_SUSPECTED
    assert feed(sm, "e1", [True]) == FaultState.FAULT_SUSPECTED
    # streak 4 -> still FAULT_SUSPECTED (threshold is 5)
    assert feed(sm, "e1", [True]) == FaultState.FAULT_SUSPECTED
    # streak 5 -> FAULT_CONFIRMED
    assert feed(sm, "e1", [True]) == FaultState.FAULT_CONFIRMED
    # sustained abnormal keeps it confirmed
    assert feed(sm, "e1", [True, True]) == FaultState.FAULT_CONFIRMED


def test_streak_broken_before_confirmation_resets_to_normal():
    sm = make_sm()
    feed(sm, "e1", [True, True])  # ANOMALY_DETECTED, streak 2 (not yet suspected)
    state = sm.update("e1", is_abnormal=False)
    assert state == FaultState.NORMAL
    # confirms the reset is real, not just cosmetic — the next abnormal
    # reading starts a fresh streak from 1, not from where it left off.
    assert sm.update("e1", is_abnormal=True) == FaultState.ANOMALY_DETECTED


def test_streak_broken_while_suspected_also_resets_to_normal():
    sm = make_sm()
    feed(sm, "e1", [True, True, True, True])  # FAULT_SUSPECTED, streak 4
    state = sm.update("e1", is_abnormal=False)
    assert state == FaultState.NORMAL


def test_confirmed_recovers_after_sustained_normal_streak():
    sm = make_sm()
    feed(sm, "e1", [True] * 5)  # FAULT_CONFIRMED
    assert feed(sm, "e1", [False, False]) == FaultState.FAULT_CONFIRMED  # not yet enough
    assert feed(sm, "e1", [False]) == FaultState.RECOVERED  # 3rd consecutive normal


def test_recovered_then_normal_reading_settles_to_normal():
    sm = make_sm()
    feed(sm, "e1", [True] * 5 + [False] * 3)  # -> RECOVERED
    assert sm.update("e1", is_abnormal=False) == FaultState.NORMAL


def test_recovered_then_abnormal_reading_starts_a_new_anomaly():
    sm = make_sm()
    feed(sm, "e1", [True] * 5 + [False] * 3)  # -> RECOVERED
    assert sm.update("e1", is_abnormal=True) == FaultState.ANOMALY_DETECTED


def test_single_normal_reading_interrupts_confirmed_recovery_streak():
    sm = make_sm()
    feed(sm, "e1", [True] * 5)  # FAULT_CONFIRMED
    feed(sm, "e1", [False, False])  # normal_streak = 2
    assert sm.update("e1", is_abnormal=True) == FaultState.FAULT_CONFIRMED  # streak broken, still confirmed
    # recovery must now start over from zero
    assert feed(sm, "e1", [False, False]) == FaultState.FAULT_CONFIRMED  # only 2 of 3 again


def test_abstention_leaves_state_and_streaks_untouched():
    sm = make_sm()
    feed(sm, "e1", [True, True])  # ANOMALY_DETECTED, streak 2
    state = sm.update("e1", is_abnormal=None)  # abstain
    assert state == FaultState.ANOMALY_DETECTED
    # the streak was preserved across the abstention — one more abnormal
    # reading completes the streak-of-3 to FAULT_SUSPECTED.
    assert sm.update("e1", is_abnormal=True) == FaultState.FAULT_SUSPECTED


def test_engines_are_tracked_independently():
    sm = make_sm()
    feed(sm, "e1", [True] * 5)  # e1 -> FAULT_CONFIRMED
    assert sm.update("e2", is_abnormal=False) == FaultState.NORMAL
    assert sm.update("e1", is_abnormal=True) == FaultState.FAULT_CONFIRMED


def test_reset_engine_clears_only_that_engines_state():
    sm = make_sm()
    feed(sm, "e1", [True] * 5)  # FAULT_CONFIRMED
    feed(sm, "e2", [True] * 5)  # FAULT_CONFIRMED
    sm.reset_engine("e1")
    assert sm.update("e1", is_abnormal=False) == FaultState.NORMAL  # fresh tracker
    assert sm.update("e2", is_abnormal=True) == FaultState.FAULT_CONFIRMED  # untouched
