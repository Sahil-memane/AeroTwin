"""
Reusable mission envelope presets — named `environmental_profile` dicts
consumed by `simulation.scenario_generator.generate_what_if_telemetry`.
A caller may also supply an arbitrary custom profile with the same keys
instead of a preset name.
"""

MISSION_PROFILES: dict[str, dict] = {
    "nominal_cruise": {
        "altitude_m": 1500.0,
        "ambient_temp_c": 15.0,
        "airspeed_mps": 45.0,
        "throttle_pattern": "climb_cruise_descent",
        "peak_throttle": 0.75,
    },
    "hot_weather_endurance": {
        "altitude_m": 500.0,
        "ambient_temp_c": 45.0,
        "airspeed_mps": 40.0,
        "throttle_pattern": "climb_cruise_descent",
        "peak_throttle": 0.85,
    },
    "high_altitude_patrol": {
        "altitude_m": 6000.0,
        "ambient_temp_c": -10.0,
        "airspeed_mps": 55.0,
        "throttle_pattern": "climb_cruise_descent",
        "peak_throttle": 0.9,
    },
    "aggressive_throttle": {
        "altitude_m": 1000.0,
        "ambient_temp_c": 25.0,
        "airspeed_mps": 50.0,
        "throttle_pattern": "aggressive",
        "peak_throttle": 1.0,
    },
}


def resolve_profile(profile: dict) -> dict:
    """
    A profile may reference a preset by name (`{"preset": "hot_weather_endurance"}`,
    optionally overriding individual keys) or be a fully custom dict already.
    """
    if "preset" in profile:
        base = dict(MISSION_PROFILES.get(profile["preset"], MISSION_PROFILES["nominal_cruise"]))
        base.update({k: v for k, v in profile.items() if k != "preset"})
        return base
    return profile
