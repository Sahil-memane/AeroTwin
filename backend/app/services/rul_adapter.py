"""
RUL Translating Adapter — maps piston-engine telemetry to C-MAPSS turbofan format.

This is the "domain gap bridge" between our Rotax 912/914 piston-engine
digital twin and the XGBoost RUL model trained on NASA C-MAPSS turbofan
data.  It translates our degradation signals (deviation_score, vibration,
CHT, EGT, etc.) into the 24-column C-MAPSS feature vector that the
XGBoost model expects.

Design rationale:
  - The adapter is a pure, stateless function — no side effects, no state.
  - It uses linear interpolation to map piston sensor values into their
    corresponding C-MAPSS sensor ranges, using the trained model's own
    input_ranges.csv as the source of truth.
  - The top-importance features (s_11, s_4, s_17, s_3) are directly
    driven by our strongest degradation indicators (deviation_score,
    vibration_magnitude, CHT, EGT), ensuring that injected faults
    produce a visible RUL drop.
"""

from __future__ import annotations

from typing import Dict, List


# ── C-MAPSS sensor nominal ranges (from input_ranges.csv) ───────────
# Each entry is (min, max) from the actual training data
CMAPSS_RANGES: Dict[str, tuple] = {
    "setting_1":  (-0.0087,  42.008),
    "setting_2":  (-0.0006,   0.842),
    "setting_3":  (60.0,    100.0),
    "s_1":        (445.0,   518.67),
    "s_2":        (535.48,  645.11),
    "s_3":        (1242.67, 1616.91),
    "s_4":        (1023.77, 1441.49),
    "s_5":        (3.91,     14.62),
    "s_6":        (5.67,     21.61),
    "s_7":        (136.17,  570.81),
    "s_8":        (1914.72, 2388.64),
    "s_9":        (7984.51, 9244.59),
    "s_10":       (0.93,      1.32),
    "s_11":       (36.04,    48.53),
    "s_12":       (128.31,  537.49),
    "s_13":       (2027.57, 2390.49),
    "s_14":       (7845.78, 8293.72),
    "s_15":       (8.1563,   11.0669),
    "s_16":       (0.02,      0.03),
    "s_17":       (302.0,   400.0),
    "s_18":       (1915.0,  2388.0),
    "s_19":       (84.93,   100.0),
    "s_20":       (10.16,    39.89),
    "s_21":       (6.0105,   23.9505),
}

# Column order expected by the XGBoost model
CMAPSS_COLUMNS: List[str] = [
    "setting_1", "setting_2", "setting_3",
    "s_1", "s_2", "s_3", "s_4", "s_5", "s_6", "s_7",
    "s_8", "s_9", "s_10", "s_11", "s_12", "s_13", "s_14",
    "s_15", "s_16", "s_17", "s_18", "s_19", "s_20", "s_21",
]


# ── Piston-engine input ranges (what our simulator emits) ────────────
# Used to normalize each piston field to [0, 1] before mapping
PISTON_RANGES: Dict[str, tuple] = {
    "rpm":                 (0.0,    5800.0),
    "throttle":            (0.0,       1.0),
    "altitude_m":          (0.0,    5000.0),
    "cht":                 (50.0,    350.0),     # °C (includes fault upper bound)
    "egt":                 (200.0,   900.0),     # °C
    "oil_pressure":        (10.0,    120.0),     # psi
    "oil_temp":            (40.0,    150.0),     # °C
    "fuel_flow":           (0.0,     20.0),      # GPH
    "vibration_magnitude": (0.0,     15.0),      # scalar
    "deviation_score":     (0.0,      3.0),      # dimensionless, >1.0 = fault
}


def _normalize(value: float, lo: float, hi: float) -> float:
    """Normalize *value* from [lo, hi] into [0, 1], clamped."""
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _lerp(t: float, lo: float, hi: float) -> float:
    """Linearly interpolate between lo and hi using t ∈ [0, 1]."""
    return lo + t * (hi - lo)


def _map_sensor(piston_value: float, piston_range: tuple, cmapss_key: str) -> float:
    """
    Map a single piston-engine value to its corresponding C-MAPSS sensor range.

    Normalizes the piston value to [0, 1] using PISTON_RANGES, then
    linearly interpolates into the CMAPSS_RANGES for the target sensor.
    """
    t = _normalize(piston_value, piston_range[0], piston_range[1])
    lo, hi = CMAPSS_RANGES[cmapss_key]
    return _lerp(t, lo, hi)


# ── Core mapping function ────────────────────────────────────────────

def piston_to_cmapss(reading: dict) -> dict:
    """
    Translate a piston-engine telemetry reading into a C-MAPSS-format
    24-column dict suitable for the XGBoost RUL model.

    Parameters
    ----------
    reading : dict
        Must contain: ``rpm``, ``cht``, ``egt``, ``oil_pressure``,
        ``oil_temp``, ``fuel_flow``.
        Should contain (will use defaults otherwise): ``throttle``,
        ``altitude_m``, ``vibration_magnitude``, ``deviation_score``.

    Returns
    -------
    dict
        Keys: ``setting_1`` … ``s_21`` (24 entries), in C-MAPSS ranges.
    """
    # Extract piston values with safe defaults
    rpm        = reading.get("rpm", 2400.0)
    throttle   = reading.get("throttle", 0.5)
    altitude_m = reading.get("altitude_m", 0.0)
    cht        = reading.get("cht", 120.0)
    egt        = reading.get("egt", 600.0)
    oil_p      = reading.get("oil_pressure", 60.0)
    oil_t      = reading.get("oil_temp", 90.0)
    fuel       = reading.get("fuel_flow", 8.0)
    vib_mag    = reading.get("vibration_magnitude", 0.5)
    dev_score  = reading.get("deviation_score", 0.0)

    # ── Settings: direct physical analogues ───────────────────────────
    # setting_1 = altitude (kft in C-MAPSS; we convert m → kft)
    altitude_kft = altitude_m * 3.28084 / 1000.0
    setting_1 = max(-0.0087, min(42.008, altitude_kft))

    # setting_2 = Mach number proxy (derived from throttle/RPM combo)
    mach_proxy = throttle * 0.842 * (rpm / PISTON_RANGES["rpm"][1])
    setting_2 = max(-0.0006, min(0.842, mach_proxy))

    # setting_3 = throttle resolver angle (60–100%)
    setting_3 = _lerp(throttle, 60.0, 100.0)

    # ── Sensor mapping ────────────────────────────────────────────────
    #
    # Strategy: the top-importance sensors are mapped from our strongest
    # degradation signals, so that engine faults produce the largest
    # XGBoost-visible feature shifts.
    #
    # Importance rank → mapping source:
    #   s_11 (27.4%)  ← deviation_score   (highest diagnostic power)
    #   s_4  (19.1%)  ← CHT               (cylinder head temperature)
    #   s_17 (16.8%)  ← vibration_magnitude
    #   s_3  ( 6.9%)  ← EGT               (exhaust gas temperature)
    #   s_9  ( 3.5%)  ← RPM               (core speed analogue)
    #
    # Remaining sensors are mapped from secondary piston telemetry.

    result = {}
    result["setting_1"] = round(setting_1, 4)
    result["setting_2"] = round(setting_2, 4)
    result["setting_3"] = round(setting_3, 4)

    # ── Top importance sensors (carefully mapped) ─────────────────────

    # s_11: HPC outlet static pressure ← deviation_score
    # This is the #1 importance feature.  As the engine deviates from
    # expected physics, this sensor shifts proportionally.
    result["s_11"] = round(_map_sensor(dev_score, PISTON_RANGES["deviation_score"], "s_11"), 4)

    # s_4: LPT outlet total temperature ← CHT
    result["s_4"] = round(_map_sensor(cht, PISTON_RANGES["cht"], "s_4"), 4)

    # s_17: bleed enthalpy ← vibration_magnitude
    result["s_17"] = round(_map_sensor(vib_mag, PISTON_RANGES["vibration_magnitude"], "s_17"), 4)

    # s_3: HPC outlet total temperature ← EGT
    result["s_3"] = round(_map_sensor(egt, PISTON_RANGES["egt"], "s_3"), 4)

    # s_9: Physical core speed ← RPM
    result["s_9"] = round(_map_sensor(rpm, PISTON_RANGES["rpm"], "s_9"), 4)

    # ── Secondary sensors ─────────────────────────────────────────────
    # s_1: Fan inlet total temp ← ambient (proxy via altitude)
    result["s_1"] = round(_map_sensor(altitude_m, PISTON_RANGES["altitude_m"], "s_1"), 4)

    # s_2: LPC outlet total temp ← oil_temp
    result["s_2"] = round(_map_sensor(oil_t, PISTON_RANGES["oil_temp"], "s_2"), 4)

    # s_5: Fan inlet pressure ← throttle
    result["s_5"] = round(_map_sensor(throttle, PISTON_RANGES["throttle"], "s_5"), 4)

    # s_6: Bypass duct pressure ← throttle (secondary)
    result["s_6"] = round(_map_sensor(throttle, PISTON_RANGES["throttle"], "s_6"), 4)

    # s_7: HPC outlet pressure ← oil_pressure
    result["s_7"] = round(_map_sensor(oil_p, PISTON_RANGES["oil_pressure"], "s_7"), 4)

    # s_8: Physical fan speed ← RPM (scaled down)
    result["s_8"] = round(_map_sensor(rpm, PISTON_RANGES["rpm"], "s_8"), 4)

    # s_10: EPR (engine pressure ratio) ← fuel_flow
    result["s_10"] = round(_map_sensor(fuel, PISTON_RANGES["fuel_flow"], "s_10"), 4)

    # s_12: Fuel flow ratio ← fuel_flow
    result["s_12"] = round(_map_sensor(fuel, PISTON_RANGES["fuel_flow"], "s_12"), 4)

    # s_13: Corrected fan speed ← RPM
    result["s_13"] = round(_map_sensor(rpm, PISTON_RANGES["rpm"], "s_13"), 4)

    # s_14: Corrected core speed ← RPM
    result["s_14"] = round(_map_sensor(rpm, PISTON_RANGES["rpm"], "s_14"), 4)

    # s_15: Bypass ratio ← throttle (inverse: higher throttle = lower bypass)
    t_inv = 1.0 - _normalize(throttle, 0.0, 1.0)
    result["s_15"] = round(_lerp(t_inv, *CMAPSS_RANGES["s_15"]), 4)

    # s_16: Burner fuel-air ratio ← fuel_flow (tiny range)
    result["s_16"] = round(_map_sensor(fuel, PISTON_RANGES["fuel_flow"], "s_16"), 4)

    # s_18: Required fan speed ← RPM
    result["s_18"] = round(_map_sensor(rpm, PISTON_RANGES["rpm"], "s_18"), 4)

    # s_19: Required fan conversion speed ← throttle
    result["s_19"] = round(_map_sensor(throttle, PISTON_RANGES["throttle"], "s_19"), 4)

    # s_20: HP turbine cool air flow ← oil_pressure
    result["s_20"] = round(_map_sensor(oil_p, PISTON_RANGES["oil_pressure"], "s_20"), 4)

    # s_21: LP turbine cool air flow ← fuel_flow
    result["s_21"] = round(_map_sensor(fuel, PISTON_RANGES["fuel_flow"], "s_21"), 4)

    return result


def piston_to_cmapss_array(reading: dict) -> list:
    """
    Same as ``piston_to_cmapss`` but returns a flat list in the canonical
    column order expected by the XGBoost model.
    """
    mapped = piston_to_cmapss(reading)
    return [mapped[col] for col in CMAPSS_COLUMNS]
