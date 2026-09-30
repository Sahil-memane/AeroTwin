"""
Context Selector — decides, per query, whether ChromaDB is needed,
whether the live backend is needed, and (if so) exactly which fields to
fetch. This is what keeps the Copilot from ever sending an entire
knowledge base or an entire engine record to the LLM: everything here
returns the smallest context that answers the question, never "just
fetch everything to be safe."

    User Query -> classify_intent() -> "static" | "live" | "combined"
               -> resolve_engine_reference() -> engine row | "unknown" | None
               -> build_live_context() -> a handful of fields, not a record dump

Deliberately keyword/regex-based rather than a second LLM call: an
intent-classification LLM call would double latency and cost for every
single question, which cuts directly against this feature's whole
point (reducing token usage).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.engine import Engine
from app.models.health_score import HealthScore
from app.models.rul_prediction import RulPrediction
from app.models.fault_prediction import FaultPrediction
from app.models.bearing_health_reading import BearingHealthReading
from app.models.aux_prediction import AuxPrediction
from app.models.telemetry_reading import TelemetryReading
from app.services.fault_reliability import is_reliable

# ── Field keyword map: which live fields a question is asking about ──
FIELD_KEYWORDS = {
    "rul": ("rul", "remaining useful life", "cycles remaining", "degradation"),
    "rpm": ("rpm", "engine speed", "rotational speed"),
    "cht": ("cht", "cylinder head temp"),
    "egt": ("egt", "exhaust gas temp"),
    "oil_pressure": ("oil pressure",),
    "oil_temp": ("oil temp",),
    "fuel_flow": ("fuel flow",),
    "vibration": ("vibration",),
    "health": ("health score", "health", "overall condition"),
    "fault": ("fault", "failure status", "failure mode"),
    "bearing": ("bearing",),
    "aux": ("auxiliary", " aux ", "heat dissipation", "power failure"),
}
GENERIC_LIVE_PHRASES = ("current status", "current condition", "how is", "condition of", "status of")

_EXPLANATION_CUE_RE = re.compile(
    r"\bwhat does\b|\bwhy\b|\bhow does\b.*\bwork\b|\bexplain\b|\bmeaning\b|\bindicate\b|\bmeans?\b",
    re.IGNORECASE,
)
# Identifier-shaped tokens: "SIM-ENGINE-01", "UNKNOWN-ENGINE", "ENG-001" —
# a letter run, a hyphen/underscore, then another alnum run.
_ENGINE_TOKEN_RE = re.compile(r"\b[A-Za-z]{2,}[-_][A-Za-z0-9][A-Za-z0-9-_]*\b")
_LIVE_QUALIFIER_RE = re.compile(r"\bcurrent(ly)?\b|\bright now\b|\bat the moment\b|\blive\b|\bnow\b|\breading\b", re.IGNORECASE)


def classify_intent(message: str) -> tuple[str, set]:
    """Returns (intent, requested_fields). intent is 'static', 'live', or
    'combined'. requested_fields is which live fields (if any) matter.

    A bare field keyword is NOT enough on its own — "What is RUL?" and
    "What is Health Fusion?" both contain a FIELD_KEYWORDS hit ("rul",
    "health") despite being pure definitional questions with no engine
    in sight. A live/combined intent additionally requires either an
    engine actually named in THIS message's own text (independent of
    any ambient engine_id the frontend may have passed — that hint is
    only used later, to resolve *which* engine, never to decide
    *whether* this is a live question) or an explicit current/now/live
    qualifier word.

    Conversely, naming a real engine is ALSO sufficient on its own, even
    with no field keyword at all — "What is SIM-ENGINE-01?" has nothing
    for ChromaDB to match (a specific instance's serial number isn't
    documentation), so it must go to the live path with a default
    summary rather than getting a correctly-grounded but useless "not in
    the knowledge base" answer.
    """
    lower = message.lower()
    requested = {key for key, kws in FIELD_KEYWORDS.items() if any(kw in lower for kw in kws)}
    mentions_engine = bool(_ENGINE_TOKEN_RE.search(message))
    has_qualifier = bool(_LIVE_QUALIFIER_RE.search(lower)) or any(p in lower for p in GENERIC_LIVE_PHRASES)
    has_live_signal = mentions_engine or (bool(requested) and has_qualifier)
    has_explanation_cue = bool(_EXPLANATION_CUE_RE.search(lower))

    if has_live_signal:
        if not requested:
            requested = {"health"}  # generic "how is it doing" -> the summary score
        return ("combined" if has_explanation_cue else "live"), requested
    return "static", set()


@dataclass
class EngineRef:
    id: str
    serial_number: str


async def resolve_engine_reference(message: str, engine_id_hint: Optional[str]) -> Optional[EngineRef] | str:
    """
    Returns an EngineRef if a real engine is identified, the string
    "unknown" if the message names something that looks like an engine
    but doesn't match any real one (so the caller can say so plainly
    instead of guessing), or None if no engine is referenced at all.
    """
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Engine.id, Engine.serial_number))).all()

    by_serial = {r.serial_number.lower(): r for r in rows}

    for token in _ENGINE_TOKEN_RE.findall(message):
        match = by_serial.get(token.lower())
        if match:
            return EngineRef(id=str(match.id), serial_number=match.serial_number)
    # A token that *looks* like an engine name but matched nothing real.
    if _ENGINE_TOKEN_RE.search(message):
        return "unknown"

    if engine_id_hint:
        async with AsyncSessionLocal() as session:
            row = (await session.execute(select(Engine).where(Engine.id == engine_id_hint))).scalars().first()
        if row:
            return EngineRef(id=str(row.id), serial_number=row.serial_number)

    return None


async def build_live_context(engine_ref: EngineRef, requested_fields: set) -> dict:
    """Fetches ONLY the latest rows needed for the requested fields —
    never a history, never unrelated tables. Returns a small dict ready
    to be dropped straight into the prompt."""
    context: dict = {"engine": engine_ref.serial_number}
    telemetry_fields = {"rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow", "vibration"}

    async with AsyncSessionLocal() as session:
        if "rul" in requested_fields:
            row = (await session.execute(
                select(RulPrediction).where(RulPrediction.engine_id == engine_ref.id)
                .order_by(RulPrediction.ts.desc()).limit(1)
            )).scalars().first()
            context["rul_cycles"] = row.rul_cycles if row else None
            context["degradation_index"] = row.degradation_index if row else None

        if "health" in requested_fields:
            row = (await session.execute(
                select(HealthScore).where(HealthScore.engine_id == engine_ref.id)
                .order_by(HealthScore.ts.desc()).limit(1)
            )).scalars().first()
            context["health_score"] = row.combined_score if row else None
            context["contributing_factors"] = row.contributing_factors if row else []

        if "fault" in requested_fields:
            row = (await session.execute(
                select(FaultPrediction).where(FaultPrediction.engine_id == engine_ref.id)
                .order_by(FaultPrediction.ts.desc()).limit(1)
            )).scalars().first()
            context["fault_class"] = row.fault_class if row else None
            context["fault_confidence"] = row.confidence if row else None
            if row is not None:
                context["fault_input_coverage"] = row.input_coverage
                context["fault_reliable"] = is_reliable(row.input_coverage)
                if not is_reliable(row.input_coverage):
                    pct = f"{row.input_coverage * 100:.0f}%" if row.input_coverage is not None else "a low share"
                    # Stated as a hard constraint so the answer can't present an
                    # out-of-distribution result as a confirmed engine fault.
                    context["fault_note"] = (
                        f"ADVISORY ONLY — the fault model was fed mostly placeholder channels (only {pct} of its 32 inputs "
                        "are measured for a piston engine). This result is NOT used in the health score or alerts. "
                        "Do not present it as a confirmed engine fault; say it is an unreliable advisory output."
                    )

        if "bearing" in requested_fields:
            row = (await session.execute(
                select(BearingHealthReading).where(BearingHealthReading.engine_id == engine_ref.id)
                .order_by(BearingHealthReading.ts.desc()).limit(1)
            )).scalars().first()
            context["bearing_condition"] = row.class_label if row else None
            context["bearing_location"] = row.fault_location if row else None
            context["bearing_severity_inches"] = row.severity_inches if row else None

        if "aux" in requested_fields:
            row = (await session.execute(
                select(AuxPrediction).where(AuxPrediction.engine_id == engine_ref.id)
                .order_by(AuxPrediction.ts.desc()).limit(1)
            )).scalars().first()
            context["aux_risk_level"] = row.risk_level if row else None
            context["aux_failure_probability_pct"] = row.failure_probability_pct if row else None
            context["aux_primary_cause"] = row.primary_failure_cause if row else None

        if requested_fields & telemetry_fields:
            row = (await session.execute(
                select(TelemetryReading).where(TelemetryReading.engine_id == engine_ref.id)
                .order_by(TelemetryReading.ts.desc()).limit(1)
            )).scalars().first()
            if row:
                context["telemetry_ts"] = row.ts.isoformat()
                for field in requested_fields & telemetry_fields:
                    if field == "vibration":
                        context["vibration_x"] = row.vibration_x
                        context["vibration_y"] = row.vibration_y
                        context["vibration_z"] = row.vibration_z
                    else:
                        context[field] = getattr(row, field)

    return context
