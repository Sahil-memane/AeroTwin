"""
Physics-consistency classification — Accuracy-First Phase 4. Uses the
real Otto-cycle physics model (no mocking — it's a pure, fast, closed-
form solver) with telemetry engineered to sit at known multiples of
each channel's own tolerance band, so each status boundary is checked
exactly rather than inferred.
"""
from app.services.physics_ingestion import compute_consistency
from app.services.physics_model import compute_expected_telemetry, PARAMETER_TOLERANCES


def _nominal_reading(rpm=4200.0, throttle=0.75) -> dict:
    """A reading whose CHT/EGT/oil_pressure/oil_temp/fuel_flow are set to
    EXACTLY what the physics model expects for this rpm/throttle — i.e.
    zero residual on every channel, our known CONSISTENT baseline."""
    expected = compute_expected_telemetry({"rpm": rpm, "throttle": throttle})
    return {
        "rpm": rpm,
        "throttle": throttle,
        "cht": expected.cht,
        "egt": expected.egt,
        "oil_pressure": expected.oil_pressure,
        "oil_temp": expected.oil_temp,
        "fuel_flow": expected.fuel_flow_gph,
    }


def test_zero_residual_is_consistent_on_every_channel():
    deviation_score, results = compute_consistency(_nominal_reading())
    assert deviation_score == 0.0
    by_param = {r.parameter: r for r in results}
    assert set(by_param) == {"cht", "egt", "oil_pressure", "oil_temp", "fuel_flow"}
    for r in results:
        assert r.status == "CONSISTENT"
        assert r.residual == 0.0
        assert r.method == "documented_baseline_v1"


def test_cht_just_over_one_tolerance_is_elevated():
    reading = _nominal_reading()
    reading["cht"] += PARAMETER_TOLERANCES["cht"] * 1.1  # just past the 1x boundary
    _, results = compute_consistency(reading)
    cht = next(r for r in results if r.parameter == "cht")
    assert cht.status == "ELEVATED"
    assert cht.residual > 0


def test_cht_just_over_two_tolerances_is_review():
    reading = _nominal_reading()
    reading["cht"] += PARAMETER_TOLERANCES["cht"] * 2.1
    _, results = compute_consistency(reading)
    cht = next(r for r in results if r.parameter == "cht")
    assert cht.status == "REVIEW"


def test_cht_over_three_tolerances_is_anomaly():
    reading = _nominal_reading()
    reading["cht"] += PARAMETER_TOLERANCES["cht"] * 3.5
    _, results = compute_consistency(reading)
    cht = next(r for r in results if r.parameter == "cht")
    assert cht.status == "ANOMALY"


def test_negative_residual_is_classified_by_magnitude_not_sign():
    reading = _nominal_reading()
    reading["oil_pressure"] -= PARAMETER_TOLERANCES["oil_pressure"] * 3.5
    _, results = compute_consistency(reading)
    op = next(r for r in results if r.parameter == "oil_pressure")
    assert op.status == "ANOMALY"
    assert op.residual < 0


def test_deviation_score_reflects_all_channels_combined():
    # A single channel far out of tolerance drives up the composite
    # score even though the other 4 channels are nominal.
    reading = _nominal_reading()
    reading["egt"] += PARAMETER_TOLERANCES["egt"] * 4.0
    deviation_score, _ = compute_consistency(reading)
    assert deviation_score > 1.0  # per PhysicsDeviation's own convention: >1.0 = out of envelope
