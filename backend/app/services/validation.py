"""
Shared telemetry payload validation — used by both the MQTT ingestion
path (`app.services.ingestion`) and the REST `POST /telemetry/ingest`
path (`app.api.v1.telemetry`), so the two paths can never silently drift
on what counts as a physically plausible reading.

Accuracy-First Phase 1 (Data Quality Layer): limits moved out of a
hardcoded dict into `app/config/telemetry_limits.yaml` (documented,
editable without a code change), and validation now returns an explicit
classification rather than a bare accept/reject string:

  VALID       — nothing wrong.
  STALE       — real reading, just old. Accept, but flag.
  SUSPICIOUS  — duplicate/out-of-order/implausible-jump relative to the
                previous reading for this engine. These are heuristic
                and relative (a network gap or clock skew can trigger
                them on genuinely fine data), so — per the source
                document's own preference for graceful uncertainty over
                harsh rejection — accept and flag, don't drop.
  INVALID     — missing required field, NaN/infinite, or a value outside
                the documented physical range. Unambiguous corruption:
                reject.
"""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "telemetry_limits.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _CONFIG = yaml.safe_load(_f)

# Same shape as the original hardcoded dict — every existing lookup site
# (`for field, (lo, hi) in SENSOR_BOUNDS.items()`) works unchanged.
SENSOR_BOUNDS = {k: tuple(v) for k, v in _CONFIG["sensor_bounds"].items()}
REQUIRED_FIELDS = tuple(_CONFIG["required_fields"])
MAX_STALENESS_SECONDS: float = _CONFIG["data_quality"]["max_staleness_seconds"]
MAX_JUMP_PER_READING: dict = _CONFIG["data_quality"]["max_jump_per_reading"]


class ValidationStatus(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    SUSPICIOUS = "SUSPICIOUS"
    INVALID = "INVALID"


@dataclass
class ValidationResult:
    status: ValidationStatus
    reason: Optional[str] = None

    @property
    def rejected(self) -> bool:
        """True only for INVALID — the one status callers must drop the reading for."""
        return self.status == ValidationStatus.INVALID


def _is_bad_number(value) -> bool:
    return isinstance(value, (int, float)) and (math.isnan(value) or math.isinf(value))


def _parse_ts(value) -> datetime:
    """Mirrors exactly what `ingestion.py`/`telemetry.py` themselves
    accept for `ts` — a numeric Unix epoch OR an ISO8601 string — so
    validation can never reject a timestamp shape the ingestion paths
    actually support. [Bug found + fixed here, Accuracy-First Phase 7:
    this previously stringified ANY non-datetime value before parsing,
    so a real numeric epoch timestamp (e.g. `time.time()`, exactly what
    `ingestion.py`'s own `else: datetime.fromtimestamp(ts_raw, ...)`
    branch is built to accept) always failed as "unparseable ts" here,
    even though the exact same reading would have persisted fine.]"""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def validate_payload(data: dict, previous: Optional[dict] = None) -> ValidationResult:
    """
    Validate one telemetry reading.

    `previous`: the last reading accepted for this SAME engine, if the
    caller tracks one (see `ingestion.py`'s per-engine `_last_reading`
    state) — enables the duplicate/out-of-order/jump checks, which are
    inherently relative to another reading. Callers with no per-engine
    state (the stateless REST ingest path) omit it and simply skip those
    three checks — everything else still applies.
    """
    for required in REQUIRED_FIELDS:
        if required not in data or data[required] is None:
            return ValidationResult(ValidationStatus.INVALID, f"missing required field: {required}")

    for field_name in SENSOR_BOUNDS:
        value = data.get(field_name)
        if value is not None and _is_bad_number(value):
            return ValidationResult(ValidationStatus.INVALID, f"{field_name} is NaN/infinite")

    for field_name, (lo, hi) in SENSOR_BOUNDS.items():
        value = data.get(field_name)
        if value is None:
            continue  # optional fields (e.g. vibration_*) may be absent
        if not (lo <= value <= hi):
            return ValidationResult(ValidationStatus.INVALID, f"{field_name}={value} outside plausible range [{lo}, {hi}]")

    try:
        ts_dt = _parse_ts(data["ts"])
    except (ValueError, TypeError):
        return ValidationResult(ValidationStatus.INVALID, f"unparseable ts: {data['ts']!r}")

    if previous is not None and previous.get("ts") is not None:
        try:
            prev_ts_dt = _parse_ts(previous["ts"])
        except (ValueError, TypeError):
            prev_ts_dt = None

        if prev_ts_dt is not None:
            if ts_dt == prev_ts_dt:
                return ValidationResult(ValidationStatus.SUSPICIOUS, "duplicate timestamp for this engine")
            if ts_dt < prev_ts_dt:
                return ValidationResult(ValidationStatus.SUSPICIOUS, "reading arrived out of order (older than the previous one)")

        for field_name, max_jump in MAX_JUMP_PER_READING.items():
            prev_value = previous.get(field_name)
            curr_value = data.get(field_name)
            if prev_value is None or curr_value is None:
                continue
            delta = abs(curr_value - prev_value)
            if delta > max_jump:
                return ValidationResult(
                    ValidationStatus.SUSPICIOUS,
                    f"{field_name} jumped {delta:.1f} in one reading (max plausible {max_jump})",
                )

    age_s = (datetime.now(timezone.utc) - ts_dt).total_seconds()
    if age_s > MAX_STALENESS_SECONDS:
        return ValidationResult(ValidationStatus.STALE, f"reading is {age_s:.1f}s old (max {MAX_STALENESS_SECONDS}s)")

    return ValidationResult(ValidationStatus.VALID)
