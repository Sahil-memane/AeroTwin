"""
Accuracy-First Phase 1 — corrupted-telemetry validation matrix.

Pure unit tests against `validate_payload()` — no DB, no app, no fixtures
needed; every case in the source document's own list is covered:
missing RPM, missing EGT, NaN, infinity, stale, duplicate, out-of-order,
extreme-but-valid, impossible, partial telemetry.
"""
from datetime import datetime, timedelta, timezone

from app.services.validation import ValidationStatus, validate_payload


def _reading(**overrides) -> dict:
    # Computed fresh per call, not once at module import — pytest
    # collects all test modules up front, so a module-level "now"
    # captured at import time can be well over MAX_STALENESS_SECONDS
    # (30s) stale by the time this test actually runs deep into a
    # multi-file suite, which is exactly the kind of test-fragility bug
    # this phase's own staleness check would (correctly) flag.
    now = datetime.now(timezone.utc)
    base = {
        "engine_id": "00000000-0000-0000-0000-000000000001",
        "ts": now.isoformat(),
        "rpm": 2400.0,
        "cht": 120.0,
        "egt": 600.0,
        "oil_pressure": 60.0,
        "oil_temp": 90.0,
        "fuel_flow": 8.0,
        "vibration_x": 0.4,
        "vibration_y": 0.4,
        "vibration_z": 0.2,
    }
    base.update(overrides)
    return base


def test_normal_reading_is_valid():
    result = validate_payload(_reading())
    assert result.status == ValidationStatus.VALID
    assert not result.rejected


def test_missing_rpm_is_invalid():
    reading = _reading()
    del reading["rpm"]
    result = validate_payload(reading)
    assert result.status == ValidationStatus.INVALID
    assert result.rejected
    assert "rpm" in result.reason


def test_missing_egt_is_invalid():
    reading = _reading()
    del reading["egt"]
    result = validate_payload(reading)
    assert result.status == ValidationStatus.INVALID
    assert "egt" in result.reason


def test_partial_telemetry_missing_multiple_fields_is_invalid():
    reading = _reading()
    del reading["oil_pressure"]
    del reading["fuel_flow"]
    result = validate_payload(reading)
    assert result.rejected


def test_nan_value_is_invalid():
    result = validate_payload(_reading(cht=float("nan")))
    assert result.status == ValidationStatus.INVALID
    assert "cht" in result.reason


def test_infinity_value_is_invalid():
    result = validate_payload(_reading(egt=float("inf")))
    assert result.status == ValidationStatus.INVALID
    assert "egt" in result.reason


def test_negative_infinity_is_invalid():
    result = validate_payload(_reading(oil_pressure=float("-inf")))
    assert result.rejected


def test_impossible_value_is_invalid():
    # rpm above the documented ceiling (see telemetry_limits.yaml)
    result = validate_payload(_reading(rpm=50000.0))
    assert result.status == ValidationStatus.INVALID
    assert "rpm" in result.reason


def test_extreme_but_valid_value_is_valid():
    # High but within the documented plausible range — must NOT be flagged.
    result = validate_payload(_reading(cht=395.0, egt=950.0))
    assert result.status == ValidationStatus.VALID


def test_stale_reading_is_flagged_not_rejected():
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    result = validate_payload(_reading(ts=old_ts))
    assert result.status == ValidationStatus.STALE
    assert not result.rejected  # accepted, just flagged


def test_fresh_reading_within_staleness_window_is_valid():
    recent_ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    result = validate_payload(_reading(ts=recent_ts))
    assert result.status == ValidationStatus.VALID


def test_duplicate_timestamp_is_suspicious_not_rejected():
    reading = _reading()
    result = validate_payload(reading, previous=reading)
    assert result.status == ValidationStatus.SUSPICIOUS
    assert not result.rejected
    assert "duplicate" in result.reason


def test_out_of_order_reading_is_suspicious():
    now = datetime.now(timezone.utc)
    previous = _reading(ts=now.isoformat())
    earlier = _reading(ts=(now - timedelta(seconds=10)).isoformat())
    result = validate_payload(earlier, previous=previous)
    assert result.status == ValidationStatus.SUSPICIOUS
    assert "out of order" in result.reason


def test_in_order_reading_after_previous_is_valid():
    now = datetime.now(timezone.utc)
    previous = _reading(ts=(now - timedelta(seconds=1)).isoformat())
    current = _reading(ts=now.isoformat())
    result = validate_payload(current, previous=previous)
    assert result.status == ValidationStatus.VALID


def test_implausible_jump_is_suspicious_not_rejected():
    now = datetime.now(timezone.utc)
    previous = _reading(rpm=2400.0, ts=(now - timedelta(seconds=1)).isoformat())
    current = _reading(rpm=5800.0, ts=now.isoformat())  # +3400 rpm in ~1s
    result = validate_payload(current, previous=previous)
    assert result.status == ValidationStatus.SUSPICIOUS
    assert not result.rejected
    assert "jumped" in result.reason


def test_plausible_change_between_readings_is_valid():
    now = datetime.now(timezone.utc)
    previous = _reading(rpm=2400.0, ts=(now - timedelta(seconds=1)).isoformat())
    current = _reading(rpm=2500.0, ts=now.isoformat())  # +100 rpm — fine
    result = validate_payload(current, previous=previous)
    assert result.status == ValidationStatus.VALID


def test_no_previous_reading_skips_relative_checks():
    # The stateless REST path has no `previous` — duplicate/order/jump
    # checks must not run, only the absolute checks.
    result = validate_payload(_reading(), previous=None)
    assert result.status == ValidationStatus.VALID


def test_optional_vibration_fields_may_be_absent():
    reading = _reading()
    del reading["vibration_x"]
    del reading["vibration_y"]
    del reading["vibration_z"]
    result = validate_payload(reading)
    assert result.status == ValidationStatus.VALID


def test_numeric_epoch_timestamp_is_valid():
    """Bug found + fixed via a Phase 7 E2E script (Scenario F): a real
    numeric Unix epoch `ts` (e.g. `time.time()`) — exactly what
    `ingestion.py`'s own `else: datetime.fromtimestamp(...)` branch is
    built to accept — previously failed here as "unparseable ts"
    because `_parse_ts` stringified any non-datetime value before
    attempting an ISO8601 parse, with no numeric branch at all."""
    reading = _reading(ts=datetime.now(timezone.utc).timestamp())
    result = validate_payload(reading)
    assert result.status == ValidationStatus.VALID


def test_stale_numeric_epoch_timestamp_is_flagged():
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
    result = validate_payload(_reading(ts=old))
    assert result.status == ValidationStatus.STALE
