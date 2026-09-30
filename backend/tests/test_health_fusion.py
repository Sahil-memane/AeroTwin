"""
Table-driven tests for the Health Fusion scoring algorithm — pure unit
tests, no DB needed, using lightweight stand-ins for the 4 prediction
rows (only the attributes `compute_health_score` actually reads).
"""
from types import SimpleNamespace

from app.services.health_fusion import compute_health_score, bearing_severity_to_points


def rul(rul_cycles, degradation_index):
    return SimpleNamespace(rul_cycles=rul_cycles, degradation_index=degradation_index)


def fault(fault_class, confidence, state=None):
    return SimpleNamespace(fault_class=fault_class, confidence=confidence, state=state)


def bearing(class_label, fault_location, severity_inches):
    return SimpleNamespace(class_label=class_label, fault_location=fault_location, severity_inches=severity_inches)


def aux(failure_probability_pct, primary_failure_cause=None, detected_failure_types=None):
    return SimpleNamespace(
        failure_probability_pct=failure_probability_pct,
        primary_failure_cause=primary_failure_cause,
        detected_failure_types=detected_failure_types or [],
    )


def test_no_predictions_yields_perfect_score():
    result = compute_health_score(None, None, None, None)
    assert result.combined_score == 100.0
    assert result.contributing_factors == []
    assert result.forced_zero is False


def test_rul_penalty_only_applies_below_50_cycles():
    healthy = compute_health_score(rul(80, 0.1), None, None, None)
    assert healthy.combined_score == 100.0

    degraded = compute_health_score(rul(10, 1.0), None, None, None)
    assert degraded.combined_score == 70.0  # 100 - min(30, 1.0*30)
    assert degraded.contributing_factors[0]["source"] == "rul"


def test_rul_penalty_scales_with_degradation_index_and_caps_at_30():
    result = compute_health_score(rul(5, 2.0), None, None, None)  # degradation_index > 1 shouldn't happen, but cap anyway
    assert result.combined_score == 70.0  # min(30, 60) == 30


def test_fault_penalty_at_71pct_confidence():
    result = compute_health_score(None, fault("GPS Failure", 0.71), None, None)
    assert result.combined_score == 60.0
    assert result.forced_zero is False


def test_fault_no_penalty_at_or_below_70pct_confidence():
    result = compute_health_score(None, fault("GPS Failure", 0.70), None, None)
    assert result.combined_score == 100.0


def test_fault_forces_zero_above_90pct_confidence():
    result = compute_health_score(None, fault("Compass Failure", 0.91), None, None)
    assert result.combined_score == 0.0
    assert result.forced_zero is True


def test_no_failure_class_never_penalizes_regardless_of_confidence():
    result = compute_health_score(None, fault("No Failure", 0.99), None, None)
    assert result.combined_score == 100.0
    assert result.contributing_factors == []


# ── Accuracy-First Phase 3: state-gated fault penalty ──────────────────
# With a real `state` present, the gate is FAULT_CONFIRMED — NOT raw
# confidence — even though the confidence value alone would have
# crossed the old 70%/90% thresholds. Only a NULL `state` (a pre-Phase-3
# row) falls back to the original confidence-only behavior above.

def test_high_confidence_but_only_suspected_state_does_not_penalize():
    result = compute_health_score(None, fault("Compass Failure", 0.95, state="FAULT_SUSPECTED"), None, None)
    assert result.combined_score == 100.0
    assert result.contributing_factors == []
    assert result.forced_zero is False


def test_high_confidence_anomaly_detected_state_does_not_penalize():
    result = compute_health_score(None, fault("GPS Failure", 0.99, state="ANOMALY_DETECTED"), None, None)
    assert result.combined_score == 100.0


def test_confirmed_state_with_low_confidence_still_penalizes_40():
    # A sustained streak (state) is what gates the penalty; once
    # confirmed, confidence still decides the magnitude (forced-zero vs -40).
    result = compute_health_score(None, fault("GPS Failure", 0.72, state="FAULT_CONFIRMED"), None, None)
    assert result.combined_score == 60.0
    assert result.contributing_factors[0]["state"] == "FAULT_CONFIRMED"


def test_confirmed_state_above_90pct_confidence_forces_zero():
    result = compute_health_score(None, fault("Compass Failure", 0.95, state="FAULT_CONFIRMED"), None, None)
    assert result.combined_score == 0.0
    assert result.forced_zero is True


def test_recovered_state_does_not_penalize():
    result = compute_health_score(None, fault("Compass Failure", 0.99, state="RECOVERED"), None, None)
    assert result.combined_score == 100.0


def test_abstained_fault_class_never_penalizes_regardless_of_state():
    result = compute_health_score(
        None, fault("Unknown / insufficient evidence", 0.99, state="FAULT_CONFIRMED"), None, None
    )
    assert result.combined_score == 100.0
    assert result.contributing_factors == []


def test_bearing_severity_interpolation_anchors():
    assert bearing_severity_to_points(0.007) == 10.0
    assert bearing_severity_to_points(0.014) == 20.0
    assert bearing_severity_to_points(0.021) == 35.0
    assert bearing_severity_to_points(0.0) == 0.0
    assert bearing_severity_to_points(None) == 0.0


def test_bearing_severity_interpolates_between_anchors():
    midpoint = bearing_severity_to_points(0.0105)  # halfway between 0.007 and 0.014
    assert 14.9 < midpoint < 15.1


def test_bearing_severity_clamps_above_top_anchor():
    assert bearing_severity_to_points(0.05) == 35.0


def test_bearing_penalty_applied_in_fusion():
    result = compute_health_score(None, None, bearing("IR_014", "Inner Race", 0.014), None)
    assert result.combined_score == 80.0
    assert result.contributing_factors[0]["source"] == "bearing"


def test_bearing_normal_class_no_severity_no_penalty():
    result = compute_health_score(None, None, bearing("Normal", "None", None), None)
    assert result.combined_score == 100.0


def test_aux_penalty_above_50pct_with_sub_failure():
    result = compute_health_score(None, None, None, aux(82.0, primary_failure_cause="HDF - Heat Dissipation Failure"))
    assert result.combined_score == 80.0
    assert result.contributing_factors[0]["sub_failure"] == "HDF - Heat Dissipation Failure"


def test_aux_falls_back_to_detected_failure_types_code_when_no_primary_cause():
    result = compute_health_score(
        None, None, None, aux(60.0, primary_failure_cause=None, detected_failure_types=[{"code": "PWF"}])
    )
    assert result.contributing_factors[0]["sub_failure"] == "PWF"


def test_aux_no_penalty_at_or_below_50pct():
    result = compute_health_score(None, None, None, aux(50.0))
    assert result.combined_score == 100.0


def test_combined_penalties_stack_and_floor_at_zero():
    result = compute_health_score(
        rul(5, 1.0),                                   # -30
        fault("GPS Failure", 0.75),                     # -40
        bearing("OR_021", "Outer Race", 0.021),         # -35
        aux(90.0, primary_failure_cause="RNF - Random"),  # -20
    )
    # 100 - 30 - 40 - 35 - 20 = -25 -> floored at 0
    assert result.combined_score == 0.0
    assert result.forced_zero is False  # floored by the score math, not the >90% fault rule
    assert len(result.contributing_factors) == 4


def test_forced_zero_overrides_any_other_penalties():
    result = compute_health_score(
        rul(5, 1.0),
        fault("Compass Failure", 0.95),  # forces zero
        None,
        None,
    )
    assert result.combined_score == 0.0
    assert result.forced_zero is True


# ── Accuracy-First Phase 5: primary_concern ─────────────────────────────

def test_primary_concern_is_none_on_perfect_score():
    result = compute_health_score(None, None, None, None)
    assert result.primary_concern is None


def test_primary_concern_names_the_single_largest_penalty():
    result = compute_health_score(
        rul(10, 1.0),                                     # -30
        None,
        bearing("OR_021", "Outer Race", 0.021),            # -35 (largest)
        aux(90.0, primary_failure_cause="RNF - Random"),   # -20
    )
    assert result.primary_concern is not None
    assert "BEARING" in result.primary_concern
    assert "Outer Race" in result.primary_concern


def test_primary_concern_reflects_forced_zero_regardless_of_other_penalties():
    result = compute_health_score(
        rul(5, 1.0),                       # -30, individually larger-looking
        fault("Compass Failure", 0.95, state="FAULT_CONFIRMED"),  # forces zero
        None,
        None,
    )
    assert result.primary_concern is not None
    assert "FAULT" in result.primary_concern
    assert "forced to 0" in result.primary_concern


# ── Accuracy-First Phase 5: fault+bearing double-counting mitigation ───
# A single vibration anomaly can plausibly trigger both Fault's
# "Accelerometer Failure" and the dedicated Bearing CNN from the same
# underlying signal. Before/after comparison via the config flag.

def test_correlated_accelerometer_and_bearing_penalty_is_capped_when_dedup_enabled(monkeypatch):
    from app.services import health_fusion

    monkeypatch.setattr(health_fusion.settings, "HEALTH_FUSION_DEDUP_CORRELATED_SOURCES", True)
    result = compute_health_score(
        None,
        fault("Accelerometer Failure", 0.75, state="FAULT_CONFIRMED"),  # -40
        bearing("IR_014", "Inner Race", 0.014),                          # -20
        None,
    )
    # Capped at max(40, 20) = 40, not the naive sum of 60.
    assert result.combined_score == 60.0
    fault_f = next(f for f in result.contributing_factors if f["source"] == "fault")
    bearing_f = next(f for f in result.contributing_factors if f["source"] == "bearing")
    assert fault_f["correlated_with"] == "bearing"
    assert bearing_f["correlated_with"] == "fault"
    # Each model's OWN reported penalty stays visible/unaltered — only
    # the score arithmetic that consumes them changes.
    assert fault_f["penalty"] == 40.0
    assert bearing_f["penalty"] == 20.0


def test_correlated_penalty_is_not_capped_when_dedup_disabled(monkeypatch):
    from app.services import health_fusion

    monkeypatch.setattr(health_fusion.settings, "HEALTH_FUSION_DEDUP_CORRELATED_SOURCES", False)
    result = compute_health_score(
        None,
        fault("Accelerometer Failure", 0.75, state="FAULT_CONFIRMED"),  # -40
        bearing("IR_014", "Inner Race", 0.014),                          # -20
        None,
    )
    # Before/after: with the flag off, the naive full sum (100-40-20=40) applies.
    assert result.combined_score == 40.0
    assert "correlated_with" not in result.contributing_factors[0]


def test_dedup_does_not_apply_to_unrelated_fault_classes(monkeypatch):
    from app.services import health_fusion

    monkeypatch.setattr(health_fusion.settings, "HEALTH_FUSION_DEDUP_CORRELATED_SOURCES", True)
    result = compute_health_score(
        None,
        fault("GPS Failure", 0.75, state="FAULT_CONFIRMED"),  # -40, unrelated to bearing
        bearing("IR_014", "Inner Race", 0.014),                # -20
        None,
    )
    # Both penalties apply in full — a GPS fault and a bearing defect are
    # not the same underlying physical event, so nothing should be capped.
    assert result.combined_score == 40.0  # 100 - 40 - 20


# ── Accuracy-First Phase 5: 8-scenario synthetic validation suite ──────
# Named exactly per the source document's own scenario list.

def test_scenario_all_normal():
    result = compute_health_score(rul(90, 0.05), fault("No Failure", 0.98), bearing("Normal", "None", None), aux(5.0))
    assert result.combined_score == 100.0
    assert result.contributing_factors == []
    assert result.primary_concern is None


def test_scenario_rul_only():
    result = compute_health_score(rul(15, 0.9), fault("No Failure", 0.98), bearing("Normal", "None", None), aux(5.0))
    assert result.combined_score == 73.0  # 100 - min(30, 0.9*30)
    assert [f["source"] for f in result.contributing_factors] == ["rul"]


def test_scenario_bearing_only():
    result = compute_health_score(rul(90, 0.05), fault("No Failure", 0.98), bearing("OR_007", "Outer Race", 0.007), aux(5.0))
    assert result.combined_score == 90.0  # 100 - 10
    assert [f["source"] for f in result.contributing_factors] == ["bearing"]


def test_scenario_fault_only():
    result = compute_health_score(rul(90, 0.05), fault("GPS Failure", 0.80, state="FAULT_CONFIRMED"), bearing("Normal", "None", None), aux(5.0))
    assert result.combined_score == 60.0  # 100 - 40
    assert [f["source"] for f in result.contributing_factors] == ["fault"]


def test_scenario_aux_only():
    result = compute_health_score(rul(90, 0.05), fault("No Failure", 0.98), bearing("Normal", "None", None), aux(75.0, primary_failure_cause="HDF"))
    assert result.combined_score == 80.0  # 100 - 20
    assert [f["source"] for f in result.contributing_factors] == ["aux"]


def test_scenario_multiple_simultaneous():
    result = compute_health_score(
        rul(10, 1.0),                                       # -30
        fault("GPS Failure", 0.80, state="FAULT_CONFIRMED"),  # -40 (unrelated to bearing, no dedup)
        bearing("OR_021", "Outer Race", 0.021),               # -35
        aux(90.0, primary_failure_cause="RNF"),               # -20
    )
    # 100 - 30 - 40 - 35 - 20 = -25 -> floored at 0
    assert result.combined_score == 0.0
    assert len(result.contributing_factors) == 4


def test_scenario_missing_model_output():
    # Only RUL ever produced a prediction — Fault/Bearing/Aux are None
    # (never evaluated), which must contribute NOTHING, not a fabricated
    # "healthy" or "unhealthy" assumption.
    result = compute_health_score(rul(15, 0.9), None, None, None)
    assert result.combined_score == 73.0
    assert [f["source"] for f in result.contributing_factors] == ["rul"]


def test_scenario_invalid_telemetry():
    # Every model reported an explicit "insufficient evidence"/error
    # state rather than a fabricated confident value — none of them may
    # contribute a penalty.
    result = compute_health_score(
        SimpleNamespace(rul_cycles=0.0, degradation_index=1.0, status="MODEL_ERROR"),
        fault("Unknown / insufficient evidence", 0.99, state="ANOMALY_DETECTED"),
        None,
        None,
    )
    assert result.combined_score == 100.0
    assert result.contributing_factors == []
    assert result.primary_concern is None
