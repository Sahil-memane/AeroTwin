"""
Health Fusion — combines the 4 independent ML model outputs into a
single 0-100 Engine Health Score, per the Implementation Document's
Phase 4 "Fusion Algorithm Flow":

  1. Base score 100.
  2. RUL penalty: if rul_cycles < 50, deduct up to 30 pts, linear in
     degradation_index.
  3. Fault penalty: -40 pts if a non-"No Failure" class has >70% confidence;
     forced to 0 if confidence >90%.
  4. Bearing penalty: severity_inches -> points, interpolated between the
     documented anchors (0.007"=10, 0.014"=20, 0.021"=35).
  5. Aux penalty: -20 pts if failure_probability_pct > 50, with the
     specific sub-failure surfaced into contributing_factors.
  6. Clamp at 0; return combined_score + contributing_factors.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.rul_prediction import RulPrediction
from app.models.fault_prediction import FaultPrediction
from app.models.bearing_health_reading import BearingHealthReading
from app.models.aux_prediction import AuxPrediction
from app.services.fault_reliability import is_reliable

# Bearing severity (inches) -> point deduction. Linearly interpolated
# between anchors (and from the origin to the first anchor), clamped at
# the top anchor's value for anything more severe.
_BEARING_SEVERITY_ANCHORS = [
    (0.007, 10.0),
    (0.014, 20.0),
    (0.021, 35.0),
]


def bearing_severity_to_points(severity_inches: Optional[float]) -> float:
    if not severity_inches or severity_inches <= 0:
        return 0.0

    anchors = _BEARING_SEVERITY_ANCHORS
    if severity_inches <= anchors[0][0]:
        return (severity_inches / anchors[0][0]) * anchors[0][1]

    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if severity_inches <= x1:
            t = (severity_inches - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return anchors[-1][1]  # clamp above the top anchor


@dataclass
class HealthScoreResult:
    combined_score: float
    contributing_factors: List[Dict[str, Any]] = field(default_factory=list)
    forced_zero: bool = False
    # Accuracy-First Phase 5 — a one-line summary of whichever single
    # contributing factor is driving the score down the most, so an
    # operator (or the Copilot) doesn't have to mentally rank a JSON
    # list. `None` when there's nothing to report (a perfect score).
    primary_concern: Optional[str] = None


def _describe_factor(f: Dict[str, Any]) -> str:
    source = f["source"]
    if source == "rul":
        return f"RUL: {f['rul_cycles']} cycles remaining (-{f['penalty']} pts)"
    if source == "fault":
        if f.get("forced_zero"):
            return f"FAULT: {f['fault_class']} confirmed at {f['confidence'] * 100:.0f}% confidence — health forced to 0"
        return f"FAULT: {f['fault_class']} confirmed (-{f['penalty']} pts)"
    if source == "bearing":
        return f"BEARING: {f['class_label']} at {f['fault_location']} ({f['severity_inches']}in, -{f['penalty']} pts)"
    if source == "aux":
        return f"AUX: {f['sub_failure'] or 'elevated failure risk'} (-{f['penalty']} pts)"
    return f"{source.upper()}: contributing factor (-{f.get('penalty', 0)} pts)"


def _primary_concern(factors: List[Dict[str, Any]], forced_zero: bool) -> Optional[str]:
    if not factors:
        return None
    forced = next((f for f in factors if f.get("forced_zero")), None)
    if forced_zero and forced is not None:
        return _describe_factor(forced)
    # Otherwise the single largest individual penalty — NOT the summed
    # "combined" figure from a dedup pair (see below), since the point
    # here is "which one thing is the biggest single concern," not the
    # score's own arithmetic.
    worst = max(factors, key=lambda f: f.get("penalty", 0.0))
    return _describe_factor(worst)


def compute_health_score(
    latest_rul: Optional[RulPrediction],
    latest_fault: Optional[FaultPrediction],
    latest_bearing: Optional[BearingHealthReading],
    latest_aux: Optional[AuxPrediction],
) -> HealthScoreResult:
    score = 100.0
    factors: List[Dict[str, Any]] = []
    forced_zero = False

    # Accuracy-First Phase 2: a MODEL_ERROR row (the xgboost-unavailable
    # mock fallback, rul_service.py) is a known-fake placeholder value —
    # never let it drive a real health penalty, regardless of what the
    # number happens to be. `status` is NULL on rows written before this
    # column existed, which correctly falls through to "treat as valid"
    # (the same behavior every pre-Phase-2 row already had).
    rul_is_usable = latest_rul is not None and getattr(latest_rul, "status", None) != "MODEL_ERROR"
    if rul_is_usable and latest_rul.rul_cycles < 50:
        penalty = min(30.0, latest_rul.degradation_index * 30.0)
        score -= penalty
        factors.append({
            "source": "rul",
            "penalty": round(penalty, 2),
            "rul_cycles": latest_rul.rul_cycles,
            "degradation_index": latest_rul.degradation_index,
        })

    # Accuracy-First Phase 3: an abstained reading ("insufficient
    # evidence") never itself drives a penalty, regardless of state —
    # there is no real classification here to penalize.
    # A fault result computed mostly from placeholder channels is advisory
    # (fault_reliability): it neither penalizes nor forces the score to 0.
    if (
        latest_fault is not None
        and is_reliable(getattr(latest_fault, "input_coverage", None))
        and latest_fault.fault_class not in ("No Failure", "Unknown / insufficient evidence")
    ):
        fault_state = getattr(latest_fault, "state", None)
        # Gate on the temporal-consistency state machine (a single
        # anomalous reading is no longer enough to read as a confirmed
        # fault) rather than raw per-cycle confidence. `state` is NULL
        # only on rows written before this column existed — those fall
        # back to the original confidence-only gate, which is exactly
        # what every pre-Phase-3 row's actual historical behavior was.
        is_confirmed = (fault_state == "FAULT_CONFIRMED") if fault_state is not None else (latest_fault.confidence > 0.70)
        if is_confirmed:
            if latest_fault.confidence > 0.90:
                forced_zero = True
                factors.append({
                    "source": "fault",
                    "forced_zero": True,
                    "fault_class": latest_fault.fault_class,
                    "confidence": round(latest_fault.confidence, 4),
                    "state": fault_state,
                })
            else:
                score -= 40.0
                factors.append({
                    "source": "fault",
                    "penalty": 40.0,
                    "fault_class": latest_fault.fault_class,
                    "confidence": round(latest_fault.confidence, 4),
                    "state": fault_state,
                })

    if latest_bearing is not None and latest_bearing.severity_inches:
        penalty = bearing_severity_to_points(latest_bearing.severity_inches)
        if penalty > 0:
            score -= penalty
            factors.append({
                "source": "bearing",
                "penalty": round(penalty, 2),
                "class_label": latest_bearing.class_label,
                "fault_location": latest_bearing.fault_location,
                "severity_inches": latest_bearing.severity_inches,
            })

    if latest_aux is not None and latest_aux.failure_probability_pct > 50.0:
        score -= 20.0
        sub_failure = latest_aux.primary_failure_cause
        if not sub_failure and latest_aux.detected_failure_types:
            sub_failure = latest_aux.detected_failure_types[0].get("code")
        factors.append({
            "source": "aux",
            "penalty": 20.0,
            "failure_probability_pct": round(latest_aux.failure_probability_pct, 2),
            "sub_failure": sub_failure,
        })

    # Accuracy-First Phase 5: double-counting mitigation. A single
    # vibration anomaly can plausibly trigger BOTH Fault's "Accelerometer
    # Failure" and the dedicated Bearing CNN from the same underlying
    # signal — without this, one physical event gets penalized twice.
    # Caps their COMBINED deduction at the larger of the two individual
    # penalties, rather than silently altering either model's own
    # reported penalty (both stay visible, tagged, in contributing_factors
    # — explainability is preserved, only the arithmetic that feeds the
    # final score changes). A no-op when `forced_zero` already applies,
    # since the final score is 0 either way in that case.
    if settings.HEALTH_FUSION_DEDUP_CORRELATED_SOURCES and not forced_zero:
        fault_factor = next(
            (f for f in factors if f["source"] == "fault" and f.get("fault_class") == "Accelerometer Failure" and "penalty" in f),
            None,
        )
        bearing_factor = next((f for f in factors if f["source"] == "bearing"), None)
        if fault_factor is not None and bearing_factor is not None:
            combined = fault_factor["penalty"] + bearing_factor["penalty"]
            capped = max(fault_factor["penalty"], bearing_factor["penalty"])
            if combined > capped:
                score += (combined - capped)
                fault_factor["correlated_with"] = "bearing"
                bearing_factor["correlated_with"] = "fault"
                fault_factor["dedup_note"] = f"combined penalty capped at {capped} (would have been {combined})"

    combined_score = 0.0 if forced_zero else max(0.0, score)
    return HealthScoreResult(
        combined_score=round(combined_score, 2),
        contributing_factors=factors,
        forced_zero=forced_zero,
        primary_concern=_primary_concern(factors, forced_zero),
    )


async def _latest(session: AsyncSession, model, engine_id, as_of: Optional[datetime] = None):
    """Newest prediction row for an engine. With `as_of`, rows older than
    `as_of - HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS` are treated as absent
    (None) so stale predictions never drive a current score."""
    query = select(model).where(model.engine_id == engine_id)
    if as_of is not None:
        # Also exclude rows from the "future" of the reading being fused
        # (e.g. a replayed/backfilled reading) — only what was known then.
        query = query.where(model.ts <= as_of)
    result = await session.execute(query.order_by(model.ts.desc()).limit(1))
    row = result.scalars().first()
    if row is not None and as_of is not None:
        age = (as_of - row.ts).total_seconds()
        if age > settings.HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS:
            return None
    return row


async def fetch_latest_predictions(session: AsyncSession, engine_id, as_of: Optional[datetime] = None):
    """Fetch the most recent row from each of the 4 prediction tables for an engine.

    `as_of` (the timestamp of the reading being fused) enables the
    freshness filter above; omit it for the unfiltered legacy behavior."""
    return (
        await _latest(session, RulPrediction, engine_id, as_of),
        await _latest(session, FaultPrediction, engine_id, as_of),
        await _latest(session, BearingHealthReading, engine_id, as_of),
        await _latest(session, AuxPrediction, engine_id, as_of),
    )


def excluded_sources(latest_fault) -> List[str]:
    """Sources that DID produce output but were deliberately not scored
    (currently: a fault prediction with too little measured input coverage).
    Distinct from `missing_sources`: nothing is absent, it is set aside."""
    if latest_fault is not None and not is_reliable(getattr(latest_fault, "input_coverage", None)):
        return ["fault"]
    return []


def missing_sources(latest_rul, latest_fault, latest_bearing, latest_aux) -> List[str]:
    """Which of the four sources have no usable (present, non-placeholder)
    prediction. A missing source contributes no penalty, which is NOT the
    same as "healthy" — callers surface this so a partial assessment
    (e.g. RUL/Fault windows still warming up after a restart) isn't read
    as a clean bill of health."""
    missing = []
    if latest_rul is None or getattr(latest_rul, "status", None) == "MODEL_ERROR":
        missing.append("rul")
    if latest_fault is None:
        missing.append("fault")
    if latest_bearing is None:
        missing.append("bearing")
    if latest_aux is None:
        missing.append("aux")
    return missing
