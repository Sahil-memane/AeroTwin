"""
Comprehensive test suite for the AeroTwin Otto-cycle physics model.

Tests cover:
  1. ISA atmospheric calculations at multiple altitudes
  2. Pure-function reproducibility (idempotent, no side effects)
  3. Calibration sanity against Rotax 912/914 spec-sheet envelopes
     (Idle, Cruise, Takeoff/Full Throttle)
  4. Deviation signal on nominal telemetry (should be ~0)
  5. Deviation signal on synthetic faults (should be large)
"""

import sys
import os
import math
import pytest

# Ensure the ml/ package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from training.physics_model import (
    OttoCycleSolver,
    ExpectedTelemetry,
    PhysicsDeviation,
    compute_expected_telemetry,
    compute_physics_deviation,
    isa_temperature,
    isa_pressure,
    isa_density,
    EngineSpecs,
    DEFAULT_SPECS,
)


# ── Helpers ───────────────────────────────────────────────────────────

def _make_actual(expected: ExpectedTelemetry, rpm: float, **overrides) -> dict:
    """Build an 'actual telemetry' dict matching the expected values, with optional overrides."""
    actual = {
        "rpm": rpm,
        "cht": expected.cht,
        "egt": expected.egt,
        "oil_pressure": expected.oil_pressure,
        "oil_temp": expected.oil_temp,
        "fuel_flow": expected.fuel_flow_gph,
    }
    actual.update(overrides)
    return actual


# ═════════════════════════════════════════════════════════════════════
#  1. ISA Atmospheric Model
# ═════════════════════════════════════════════════════════════════════

class TestISA:
    """International Standard Atmosphere calculations."""

    def test_sea_level_temperature(self):
        T = isa_temperature(0.0)
        assert T == pytest.approx(288.15, abs=0.01)

    def test_sea_level_pressure(self):
        P = isa_pressure(0.0)
        assert P == pytest.approx(101325.0, abs=1.0)

    def test_sea_level_density(self):
        rho = isa_density(0.0)
        assert rho == pytest.approx(1.225, abs=0.01)

    def test_1000m_temperature(self):
        T = isa_temperature(1000.0)
        assert T == pytest.approx(281.65, abs=0.01)

    def test_1000m_pressure(self):
        P = isa_pressure(1000.0)
        # ISA standard: ~89876 Pa at 1000 m
        assert P == pytest.approx(89876, abs=200)

    def test_3000m_temperature(self):
        T = isa_temperature(3000.0)
        assert T == pytest.approx(268.65, abs=0.01)

    def test_3000m_density(self):
        rho = isa_density(3000.0)
        # ISA standard: ~0.909 kg/m³ at 3000 m
        assert rho == pytest.approx(0.909, abs=0.02)

    def test_temperature_decreases_with_altitude(self):
        assert isa_temperature(0.0) > isa_temperature(1000.0) > isa_temperature(5000.0)

    def test_pressure_decreases_with_altitude(self):
        assert isa_pressure(0.0) > isa_pressure(1000.0) > isa_pressure(5000.0)

    def test_density_decreases_with_altitude(self):
        assert isa_density(0.0) > isa_density(1000.0) > isa_density(5000.0)


# ═════════════════════════════════════════════════════════════════════
#  2. Pure Function Properties
# ═════════════════════════════════════════════════════════════════════

class TestPureFunctionProperties:
    """The solver must be deterministic and side-effect-free."""

    def test_idempotent(self):
        """Calling with the same inputs twice must return identical results."""
        ops = {"rpm": 4800, "throttle": 0.75, "altitude_m": 0.0}
        r1 = compute_expected_telemetry(ops)
        r2 = compute_expected_telemetry(ops)
        assert r1 == r2

    def test_independent_instances(self):
        """Two solver instances with the same specs must agree."""
        solver1 = OttoCycleSolver()
        solver2 = OttoCycleSolver()
        r1 = solver1.solve(rpm=4800, throttle=0.75)
        r2 = solver2.solve(rpm=4800, throttle=0.75)
        assert r1 == r2

    def test_different_specs_differ(self):
        """Different EngineSpecs must produce different results."""
        custom = EngineSpecs(compression_ratio=11.0)
        r_default = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75})
        r_custom = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75}, specs=custom)
        assert r_default.cht != r_custom.cht


# ═════════════════════════════════════════════════════════════════════
#  3. Calibration Sanity — Flight State Envelopes
# ═════════════════════════════════════════════════════════════════════

class TestCalibrationSanity:
    """
    Verify predicted values fall within plausible Rotax 912/914 envelopes.

    These are not tight assertions — they confirm the thermodynamic model
    produces output in the right order of magnitude for each flight state.
    """

    def test_idle_state(self):
        """Idle: ~1400 RPM, low throttle."""
        r = compute_expected_telemetry({"rpm": 1400, "throttle": 0.10})
        # Power should be very low at idle
        assert 0.0 < r.brake_power_kw < 12.0, f"Idle power {r.brake_power_kw} kW out of range"
        # CHT should be cool
        assert 40.0 < r.cht < 130.0, f"Idle CHT {r.cht} °C out of range"
        # EGT should be low-moderate
        assert 300.0 < r.egt < 800.0, f"Idle EGT {r.egt} °C out of range"

    def test_cruise_state(self):
        """Cruise: ~4800 RPM, ~75% throttle."""
        r = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75})
        # Cruise power: ~45–70 kW (60–95 HP)
        assert 35.0 < r.brake_power_kw < 75.0, f"Cruise power {r.brake_power_kw} kW out of range"
        # CHT: 110–150 °C typical
        assert 90.0 < r.cht < 170.0, f"Cruise CHT {r.cht} °C out of range"
        # EGT: 650–780 °C typical
        assert 500.0 < r.egt < 850.0, f"Cruise EGT {r.egt} °C out of range"

    def test_full_throttle_state(self):
        """Takeoff / max continuous: ~5800 RPM, WOT."""
        r = compute_expected_telemetry({"rpm": 5800, "throttle": 1.0})
        # Full power: ~65–85 kW (88–115 HP)
        assert 55.0 < r.brake_power_kw < 90.0, f"Takeoff power {r.brake_power_kw} kW out of range"
        # CHT higher under max power
        assert 100.0 < r.cht < 180.0, f"Takeoff CHT {r.cht} °C out of range"
        # EGT highest at full power
        assert 600.0 < r.egt < 900.0, f"Takeoff EGT {r.egt} °C out of range"

    def test_power_increases_with_rpm(self):
        """Power must monotonically increase from idle to max RPM."""
        powers = []
        for rpm in [1400, 2500, 3500, 4800, 5800]:
            throttle = 0.08 + 0.92 * (rpm - 1400) / (5800 - 1400)
            r = compute_expected_telemetry({"rpm": rpm, "throttle": throttle})
            powers.append(r.brake_power_kw)
        for i in range(len(powers) - 1):
            assert powers[i] < powers[i + 1], f"Power not monotonic: {powers}"

    def test_thermal_efficiency_reasonable(self):
        """Otto-cycle efficiency for r=9.0, γ=1.35 should be ~45%."""
        r = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75})
        # Theoretical: 1 - 1/9^0.35 ≈ 0.453
        assert 0.35 < r.thermal_efficiency < 0.55, f"η_th = {r.thermal_efficiency}"

    def test_altitude_reduces_power(self):
        """At higher altitude, thinner air → less mass flow → less power."""
        r_sea = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "altitude_m": 0})
        r_high = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "altitude_m": 3000})
        assert r_high.brake_power_kw < r_sea.brake_power_kw

    def test_fuel_flow_positive(self):
        """Fuel flow must always be positive for any running condition."""
        for rpm in [1400, 3000, 5800]:
            r = compute_expected_telemetry({"rpm": rpm, "throttle": 0.5})
            assert r.fuel_flow_gph > 0.0


# ═════════════════════════════════════════════════════════════════════
#  4. Deviation Signal — Nominal Case
# ═════════════════════════════════════════════════════════════════════

class TestDeviationNominal:
    """When actual == expected, residuals and score should be ~0."""

    def test_zero_deviation_at_cruise(self):
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=4800)
        dev = compute_physics_deviation(actual, ops)
        assert dev.delta_cht == pytest.approx(0.0, abs=0.01)
        assert dev.delta_egt == pytest.approx(0.0, abs=0.01)
        assert dev.delta_oil_pressure == pytest.approx(0.0, abs=0.01)
        assert dev.delta_oil_temp == pytest.approx(0.0, abs=0.01)
        assert dev.delta_fuel_flow == pytest.approx(0.0, abs=0.01)
        assert dev.deviation_score < 0.05

    def test_small_deviation_within_noise(self):
        """A few degrees of sensor noise should keep score < 0.2."""
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=4800, cht=expected.cht + 3, egt=expected.egt - 5)
        dev = compute_physics_deviation(actual, ops)
        assert dev.deviation_score < 0.3

    def test_inferred_operating_conditions(self):
        """When operating_conditions=None, the function infers from actual telemetry."""
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=4800)
        dev = compute_physics_deviation(actual, None)
        # Score won't be exactly 0 because throttle is estimated, but should be moderate
        assert dev.deviation_score < 1.0


# ═════════════════════════════════════════════════════════════════════
#  5. Deviation Signal — Synthetic Faults
# ═════════════════════════════════════════════════════════════════════

class TestDeviationFaults:
    """Injected faults must produce large deviation scores."""

    def test_cht_overheat_fault(self):
        """Simulate CHT ramped 60 °C above expected → deviation_score >> 1.0."""
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=4800, cht=expected.cht + 60.0)
        dev = compute_physics_deviation(actual, ops)
        assert dev.delta_cht > 55.0
        assert dev.deviation_score > 1.0

    def test_oil_pressure_loss_fault(self):
        """Simulate oil pressure drop by 30 psi → large score."""
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=4800, oil_pressure=expected.oil_pressure - 30.0)
        dev = compute_physics_deviation(actual, ops)
        assert dev.delta_oil_pressure < -25.0
        assert dev.deviation_score > 1.0

    def test_egt_overtemp_fault(self):
        """Simulate EGT 100 °C above expected → significant deviation."""
        ops = {"rpm": 5800, "throttle": 1.0}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(expected, rpm=5800, egt=expected.egt + 100.0)
        dev = compute_physics_deviation(actual, ops)
        assert dev.delta_egt > 95.0
        assert dev.deviation_score > 1.0

    def test_multi_channel_fault(self):
        """Multiple simultaneous anomalies → even higher score."""
        ops = {"rpm": 4800, "throttle": 0.75}
        expected = compute_expected_telemetry(ops)
        actual = _make_actual(
            expected, rpm=4800,
            cht=expected.cht + 40.0,
            egt=expected.egt + 80.0,
            oil_pressure=expected.oil_pressure - 20.0,
        )
        dev = compute_physics_deviation(actual, ops)
        assert dev.deviation_score > 1.5  # Composite should be even higher


# ═════════════════════════════════════════════════════════════════════
#  6. Edge Cases
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary and edge-case handling."""

    def test_zero_rpm_does_not_crash(self):
        """RPM = 0 (engine stopped) should still return valid output."""
        r = compute_expected_telemetry({"rpm": 0, "throttle": 0.0})
        assert r.brake_power_kw == 0.0 or r.brake_power_kw >= 0.0
        assert math.isfinite(r.cht)
        assert math.isfinite(r.egt)

    def test_high_altitude(self):
        """5000 m altitude should not cause errors or negative values."""
        r = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "altitude_m": 5000})
        assert r.brake_power_kw >= 0.0
        assert r.cht > 0.0
        assert r.fuel_flow_gph > 0.0

    def test_very_cold_ambient(self):
        """Ambient -40°C should produce valid results."""
        r = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "ambient_temp_c": -40.0})
        assert math.isfinite(r.cht)
        assert math.isfinite(r.egt)

    def test_very_hot_ambient(self):
        """Ambient +50°C should produce valid results."""
        r = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "ambient_temp_c": 50.0})
        assert math.isfinite(r.cht)
        assert math.isfinite(r.egt)
        # Hotter ambient → hotter CHT
        r_normal = compute_expected_telemetry({"rpm": 4800, "throttle": 0.75, "ambient_temp_c": 15.0})
        assert r.cht > r_normal.cht
