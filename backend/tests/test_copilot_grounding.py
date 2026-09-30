"""
Copilot source-tagging — Accuracy-First Phase 6 (Copilot Accuracy &
Grounding). `copilot_engine.py` lives in `AeroTwin_Rag/`, a sibling of
`app/` with no `__init__.py` (not a proper package) — importing it
requires the same sys.path insertion the real router
(`app/api/v1/copilot.py`) already does. Only the pure tagging logic is
tested here — `_CopilotEngine` itself needs a real GEMINI_API_KEY and a
built ChromaDB store to instantiate, which this test environment has
neither of (nor should a unit test need either).
"""
import os
import sys

_RAG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AeroTwin_Rag"))
if _RAG_DIR not in sys.path:
    sys.path.insert(0, _RAG_DIR)

import copilot_engine  # noqa: E402


def test_raw_telemetry_fields_are_tagged_live():
    for field in ("rpm", "cht", "egt", "oil_pressure", "oil_temp", "fuel_flow", "vibration_x", "vibration_y", "vibration_z"):
        assert copilot_engine._tag_context_line(field) == "LIVE"


def test_model_output_fields_are_tagged_prediction():
    for field in copilot_engine._PREDICTION_FIELDS:
        assert copilot_engine._tag_context_line(field) == "PREDICTION"


def test_identifier_fields_are_not_tagged():
    assert copilot_engine._tag_context_line("engine") is None
    assert copilot_engine._tag_context_line("telemetry_ts") is None


def test_every_prediction_field_is_actually_produced_by_build_live_context():
    """Guards against the tag map silently drifting from
    context_selector.build_live_context's real field set — e.g. if a
    new live field were added there without updating _PREDICTION_FIELDS,
    it would default to LIVE, which is wrong for a model output."""
    import context_selector

    source = open(os.path.join(_RAG_DIR, "context_selector.py")).read()
    for field in copilot_engine._PREDICTION_FIELDS:
        assert f'context["{field}"]' in source, f"{field} not found in build_live_context — tag map may be stale"
    assert context_selector.build_live_context  # imported successfully


def test_system_prompt_documents_all_four_source_tags():
    for tag in ("[LIVE]", "[PREDICTION]", "[DOCS]", "[SIMULATION]"):
        assert tag in copilot_engine.SYSTEM_PROMPT


# ── Advisory fault results must not reach the Copilot as confirmed facts ──

def test_fault_reliability_fields_are_tagged_as_model_output():
    for field in ("fault_input_coverage", "fault_reliable", "fault_note"):
        assert copilot_engine._tag_context_line(field) == "PREDICTION"


async def _live_fault_context(engine_id, coverage):
    import datetime as dt
    import uuid

    from app.db.session import AsyncSessionLocal
    from app.models.fault_prediction import FaultPrediction
    import context_selector

    async with AsyncSessionLocal() as db:
        db.add(FaultPrediction(
            ts=dt.datetime(2020, 1, 1, 12), engine_id=engine_id,
            model_version_id=uuid.UUID("00000000-0000-0000-0000-000000000004"), class_id=5,
            fault_class="Compass Failure", confidence=0.999, probabilities=[0.0] * 7,
            state="FAULT_CONFIRMED", input_coverage=coverage,
        ))
        await db.commit()
    return await context_selector.build_live_context(context_selector.EngineRef(id=str(engine_id), serial_number="T"), {"fault"})


async def test_copilot_context_marks_an_advisory_fault_and_forbids_presenting_it_as_confirmed(make_engine):
    engine = await make_engine()
    ctx = await _live_fault_context(engine.id, 0.46875)
    assert ctx["fault_reliable"] is False and ctx["fault_input_coverage"] == 0.46875
    note = ctx["fault_note"]
    assert "ADVISORY ONLY" in note and "47%" in note and "NOT used in the health score" in note
    assert "Do not present it as a confirmed engine fault" in note


async def test_copilot_context_has_no_advisory_note_for_a_reliable_or_legacy_fault(make_engine):
    for cov in (0.9, None):
        engine = await make_engine()
        ctx = await _live_fault_context(engine.id, cov)
        assert ctx["fault_reliable"] is True and "fault_note" not in ctx, cov

