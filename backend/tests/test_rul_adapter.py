"""
Unit tests for the RUL Translating Adapter.

Validates that the piston-to-C-MAPSS mapping:
  1. Produces all 24 expected columns
  2. Every output value lands within the C-MAPSS training ranges
  3. Nominal telemetry maps to mid-range C-MAPSS values
  4. High deviation_score shifts the #1 importance sensor (s_11) upward
  5. Fault-injected telemetry produces measurably different output
  6. The array output matches the canonical column order
"""

import sys
import os
import pytest

# Ensure the backend app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.rul_adapter import (
    piston_to_cmapss,
    piston_to_cmapss_array,
    CMAPSS_COLUMNS,
    CMAPSS_RANGES,
)


# ── Test fixtures ─────────────────────────────────────────────────────

NOMINAL_READING = {
    "rpm": 4800.0,
    "throttle": 0.75,
    "altitude_m": 2400.0,
    "cht": 135.0,
    "egt": 650.0,
    "oil_pressure": 65.0,
    "oil_temp": 95.0,
    "fuel_flow": 10.0,
    "vibration_x": 0.5,
    "vibration_y": 0.4,
    "vibration_z": 0.2,
    "vibration_magnitude": 0.67,
    "deviation_score": 0.15,
}

FAULT_CHT_OVERHEAT = {
    **NOMINAL_READING,
    "cht": 280.0,
    "deviation_score": 2.0,
}

FAULT_OIL_LOSS = {
    **NOMINAL_READING,
    "oil_pressure": 15.0,
    "deviation_score": 1.8,
}

FAULT_HIGH_VIB = {
    **NOMINAL_READING,
    "vibration_magnitude": 10.0,
    "deviation_score": 1.5,
}


# ═════════════════════════════════════════════════════════════════════
#  1. Structural Integrity
# ═════════════════════════════════════════════════════════════════════

class TestStructure:
    """The adapter must output exactly 24 columns in the right order."""

    def test_output_has_24_keys(self):
        result = piston_to_cmapss(NOMINAL_READING)
        assert len(result) == 24

    def test_all_expected_keys_present(self):
        result = piston_to_cmapss(NOMINAL_READING)
        for col in CMAPSS_COLUMNS:
            assert col in result, f"Missing column: {col}"

    def test_array_length(self):
        arr = piston_to_cmapss_array(NOMINAL_READING)
        assert len(arr) == 24

    def test_array_matches_dict_order(self):
        d = piston_to_cmapss(NOMINAL_READING)
        arr = piston_to_cmapss_array(NOMINAL_READING)
        for i, col in enumerate(CMAPSS_COLUMNS):
            assert arr[i] == d[col], f"Array index {i} ({col}) mismatch"


# ═════════════════════════════════════════════════════════════════════
#  2. Range Validity
# ═════════════════════════════════════════════════════════════════════

class TestRangeValidity:
    """Every output sensor must land within C-MAPSS training bounds."""

    @pytest.mark.parametrize("reading", [
        NOMINAL_READING,
        FAULT_CHT_OVERHEAT,
        FAULT_OIL_LOSS,
        FAULT_HIGH_VIB,
    ], ids=["nominal", "cht_overheat", "oil_loss", "high_vib"])
    def test_all_values_in_cmapss_range(self, reading):
        result = piston_to_cmapss(reading)
        for col, value in result.items():
            lo, hi = CMAPSS_RANGES[col]
            assert lo <= value <= hi, (
                f"{col}={value} outside C-MAPSS range [{lo}, {hi}]"
            )


# ═════════════════════════════════════════════════════════════════════
#  3. Nominal Mapping Sanity
# ═════════════════════════════════════════════════════════════════════

class TestNominalMapping:
    """Nominal piston telemetry should map to the middle of C-MAPSS ranges."""

    def test_setting_3_maps_from_throttle(self):
        result = piston_to_cmapss(NOMINAL_READING)
        # throttle 0.75 → setting_3 = lerp(0.75, 60, 100) = 90.0
        assert result["setting_3"] == pytest.approx(90.0, abs=0.1)

    def test_s_11_low_for_nominal_deviation(self):
        result = piston_to_cmapss(NOMINAL_READING)
        lo, hi = CMAPSS_RANGES["s_11"]
        # deviation_score 0.15 / 3.0 = 5% → should be near the bottom
        assert result["s_11"] < lo + 0.15 * (hi - lo)


# ═════════════════════════════════════════════════════════════════════
#  4. Fault Response — Top Importance Sensors
# ═════════════════════════════════════════════════════════════════════

class TestFaultResponse:
    """Injected faults must shift the top-importance C-MAPSS sensors."""

    def test_high_deviation_shifts_s11_up(self):
        """deviation_score 2.0 should push s_11 significantly higher than nominal."""
        nom = piston_to_cmapss(NOMINAL_READING)
        fault = piston_to_cmapss(FAULT_CHT_OVERHEAT)
        assert fault["s_11"] > nom["s_11"] + 3.0, (
            f"s_11 didn't shift enough: nominal={nom['s_11']}, fault={fault['s_11']}"
        )

    def test_high_cht_shifts_s4_up(self):
        """CHT overheat should push s_4 (LPT outlet temp) higher."""
        nom = piston_to_cmapss(NOMINAL_READING)
        fault = piston_to_cmapss(FAULT_CHT_OVERHEAT)
        assert fault["s_4"] > nom["s_4"]

    def test_high_vibration_shifts_s17(self):
        """High vibration should shift s_17 (bleed enthalpy) significantly."""
        nom = piston_to_cmapss(NOMINAL_READING)
        fault = piston_to_cmapss(FAULT_HIGH_VIB)
        assert fault["s_17"] > nom["s_17"] + 10.0

    def test_oil_loss_shifts_s7(self):
        """Oil pressure loss should reduce s_7 (HPC outlet pressure)."""
        nom = piston_to_cmapss(NOMINAL_READING)
        fault = piston_to_cmapss(FAULT_OIL_LOSS)
        assert fault["s_7"] < nom["s_7"]


# ═════════════════════════════════════════════════════════════════════
#  5. Specific Deviation Score Probes
# ═════════════════════════════════════════════════════════════════════

class TestDeviationScoreProbes:
    """Known deviation_score values should produce predictable s_11."""

    @pytest.mark.parametrize("dev_score,expected_fraction", [
        (0.0,  0.0),    # perfectly nominal → bottom of s_11 range
        (1.5,  0.5),    # halfway → mid-range
        (3.0,  1.0),    # max → top of s_11 range
    ])
    def test_s11_tracks_deviation_linearly(self, dev_score, expected_fraction):
        reading = {**NOMINAL_READING, "deviation_score": dev_score}
        result = piston_to_cmapss(reading)
        lo, hi = CMAPSS_RANGES["s_11"]
        expected_s11 = lo + expected_fraction * (hi - lo)
        assert result["s_11"] == pytest.approx(expected_s11, abs=0.1)


# ═════════════════════════════════════════════════════════════════════
#  6. Edge Cases
# ═════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary and missing-field handling."""

    def test_minimal_reading(self):
        """Adapter should work with only required fields (rpm, cht, etc.)."""
        minimal = {"rpm": 3000, "cht": 120, "egt": 550, "oil_pressure": 55,
                    "oil_temp": 80, "fuel_flow": 7}
        result = piston_to_cmapss(minimal)
        assert len(result) == 24

    def test_zero_rpm(self):
        """Zero RPM should not crash and should produce valid C-MAPSS ranges."""
        zero = {**NOMINAL_READING, "rpm": 0.0}
        result = piston_to_cmapss(zero)
        for col, value in result.items():
            lo, hi = CMAPSS_RANGES[col]
            assert lo <= value <= hi, f"{col}={value} out of range"

    def test_extreme_deviation(self):
        """deviation_score > 3.0 should be clamped to the top of s_11 range."""
        extreme = {**NOMINAL_READING, "deviation_score": 10.0}
        result = piston_to_cmapss(extreme)
        lo, hi = CMAPSS_RANGES["s_11"]
        assert result["s_11"] == pytest.approx(hi, abs=0.01)
