"""
Fault Detection temporal-consistency state machine — Accuracy-First
Phase 3. A single anomalous reading is common noise, not evidence of a
real fault; this tracks a per-engine streak so only a *sustained*
pattern of abnormal classifications reads as a confirmed fault.

States (per the source document): NORMAL -> ANOMALY_DETECTED ->
FAULT_SUSPECTED -> FAULT_CONFIRMED, with a RECOVERED de-escalation after
enough consecutive normal readings. SENSOR_ANOMALY is reserved for the
Tier 2 sensor-vs-engine fault isolation work (never assigned by this
state machine) — the enum value exists now so Health Fusion and the
frontend don't need a second migration when that lands.

Counts are consecutive-reading streaks, not wall-clock time, so the
thresholds stay meaningful regardless of telemetry rate.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "telemetry_limits.yaml"
with open(_CONFIG_PATH, encoding="utf-8") as _f:
    _CONFIG = yaml.safe_load(_f)

_SM_CONFIG = _CONFIG["fault_detection"]["state_machine"]


class FaultState(str, Enum):
    NORMAL = "NORMAL"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    FAULT_SUSPECTED = "FAULT_SUSPECTED"
    FAULT_CONFIRMED = "FAULT_CONFIRMED"
    RECOVERED = "RECOVERED"
    SENSOR_ANOMALY = "SENSOR_ANOMALY"


@dataclass
class _EngineFaultTracker:
    state: FaultState = FaultState.NORMAL
    abnormal_streak: int = 0
    normal_streak: int = 0


class FaultStateMachine:
    def __init__(self, anomaly_to_suspect: int, suspect_to_confirm: int, confirmed_to_recovered: int):
        self._anomaly_to_suspect = anomaly_to_suspect
        self._suspect_to_confirm = suspect_to_confirm
        self._confirmed_to_recovered = confirmed_to_recovered
        self._trackers: dict[str, _EngineFaultTracker] = {}

    def update(self, engine_id: str, is_abnormal: Optional[bool]) -> FaultState:
        """
        `is_abnormal`: True (a real fault class this cycle), False ("No
        Failure" this cycle), or None (stage-2 abstained — inconclusive;
        the streak counters are left untouched and the current state
        carries over unchanged for this one cycle, since an abstention
        is neither evidence of a fault nor evidence of normal operation).
        """
        t = self._trackers.setdefault(engine_id, _EngineFaultTracker())
        if is_abnormal is None:
            return t.state

        if is_abnormal:
            t.normal_streak = 0
            t.abnormal_streak += 1
            if t.state in (FaultState.NORMAL, FaultState.RECOVERED):
                t.state = FaultState.ANOMALY_DETECTED
            elif t.state == FaultState.ANOMALY_DETECTED and t.abnormal_streak >= self._anomaly_to_suspect:
                t.state = FaultState.FAULT_SUSPECTED
            elif t.state == FaultState.FAULT_SUSPECTED and t.abnormal_streak >= self._suspect_to_confirm:
                t.state = FaultState.FAULT_CONFIRMED
            # FAULT_CONFIRMED stays FAULT_CONFIRMED while abnormal readings continue.
        else:
            t.abnormal_streak = 0
            if t.state in (FaultState.ANOMALY_DETECTED, FaultState.FAULT_SUSPECTED):
                # The abnormal streak broke before it was ever confirmed —
                # not sustained, so it was noise. Reset straight to NORMAL
                # rather than gradually stepping back down.
                t.state = FaultState.NORMAL
                t.normal_streak = 0
            elif t.state == FaultState.FAULT_CONFIRMED:
                t.normal_streak += 1
                if t.normal_streak >= self._confirmed_to_recovered:
                    t.state = FaultState.RECOVERED
                    t.normal_streak = 0
            elif t.state == FaultState.RECOVERED:
                t.state = FaultState.NORMAL
            # NORMAL -> NORMAL: no-op.

        return t.state

    def reset_engine(self, engine_id: str) -> None:
        self._trackers.pop(engine_id, None)


fault_state_machine = FaultStateMachine(
    anomaly_to_suspect=_SM_CONFIG["anomaly_to_suspect_streak"],
    suspect_to_confirm=_SM_CONFIG["suspect_to_confirm_streak"],
    confirmed_to_recovered=_SM_CONFIG["confirmed_to_recovered_streak"],
)
