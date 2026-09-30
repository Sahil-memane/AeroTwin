"""
The fault model's input-coverage gate.

The piston adapter drives only some of the fault model's 32 UAV channels from
measured telemetry (the rest are fixed placeholders). A fault result computed
mostly from placeholders is advisory: it must not force Health Fusion to 0,
penalize the score, or raise alerts — while still being returned and shown.
"""
import datetime as dt
import math
import uuid

import numpy as np
import pytest

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.fault_prediction import FaultPrediction
from app.schemas.predictions import FaultPrediction as FaultSchema
from app.services import fault_adapter as fa, health_fusion, what_if_scenario as w
from app.services.fault_reliability import is_reliable
from app.services.fault_service import FaultService
from tests.conftest import auth_headers
from tests.test_what_if_scenario import make_window


class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _confirmed_fault(**over):
    base = dict(fault_class="Compass Failure", confidence=0.999, state="FAULT_CONFIRMED")
    base.update(over)
    return _Row(**base)


# ── adapter coverage is derived from what the adapter really does ────

def test_placeholder_channels_are_exactly_the_constant_columns():
    rng = np.random.default_rng(7)
    rows = [dict(rpm=3000 + 500 * rng.random(), cht=100 + 40 * rng.random(), egt=700 + 80 * rng.random(),
                 oil_pressure=60 + 10 * rng.random(), oil_temp=90 + 5 * rng.random(), fuel_flow=8 + 2 * rng.random(),
                 vibration_x=rng.random(), vibration_y=rng.random(), vibration_z=9.8 + rng.random()) for _ in range(60)]
    arr, prev = [], None
    for d in rows:
        arr.append(fa.piston_to_uav_telemetry(d, prev))
        prev = {"x": d["vibration_x"], "y": d["vibration_y"], "z": d["vibration_z"]}
    arr = np.array(arr)[1:]  # first row has no previous vibration for the gyro-rate channels
    constant = {fa.CHANNELS[i] for i in range(32) if arr[:, i].std() <= 1e-9}
    assert constant == set(fa.PLACEHOLDER_CHANNELS), "PLACEHOLDER_CHANNELS drifted from the adapter"


def test_input_coverage_value():
    assert len(fa.PLACEHOLDER_CHANNELS) == 17
    assert fa.input_coverage() == pytest.approx(15 / 32)


def test_is_reliable_threshold_and_legacy_null(monkeypatch):
    assert is_reliable(None) is True  # legacy rows keep legacy behavior
    monkeypatch.setattr(settings, "FAULT_MIN_INPUT_COVERAGE", 0.6)
    assert is_reliable(0.47) is False and is_reliable(0.6) is True and is_reliable(0.9) is True


# ── service output ───────────────────────────────────────────────────

def _fill_window(svc):
    out = None
    for i in range(svc.window_len):
        wig = math.sin(i * 0.9)
        out = svc.push_reading("cov", dict(rpm=3000 + 300 * wig, cht=140, egt=700, oil_pressure=70, oil_temp=92, fuel_flow=9,
                                           vibration_x=0.3 + 0.05 * wig, vibration_y=0.2, vibration_z=0.1))
    return out


def test_fault_service_reports_coverage_and_marks_it_advisory():
    svc = FaultService()
    res = _fill_window(svc)
    assert res["input_coverage"] == pytest.approx(15 / 32)
    assert res["reliable"] is False  # 0.47 < default 0.6
    svc.reset_engine("cov")


def test_fault_service_is_reliable_when_threshold_allows(monkeypatch):
    monkeypatch.setattr(settings, "FAULT_MIN_INPUT_COVERAGE", 0.4)
    svc = FaultService()
    assert _fill_window(svc)["reliable"] is True
    svc.reset_engine("cov")


# ── Health Fusion ────────────────────────────────────────────────────

def test_unreliable_confirmed_fault_neither_penalizes_nor_forces_zero():
    res = health_fusion.compute_health_score(None, _confirmed_fault(input_coverage=0.47), None, None)
    assert res.forced_zero is False and res.combined_score == 100.0
    assert res.contributing_factors == []


def test_reliable_confirmed_fault_still_forces_zero():
    for cov in (None, 0.9):  # legacy NULL, and a genuinely well-covered input
        res = health_fusion.compute_health_score(None, _confirmed_fault(input_coverage=cov), None, None)
        assert res.forced_zero is True and res.combined_score == 0.0, cov


def test_other_sources_still_score_when_fault_is_set_aside():
    aux = _Row(failure_probability_pct=60.0, primary_failure_cause="HDF", detected_failure_types=[])
    res = health_fusion.compute_health_score(None, _confirmed_fault(input_coverage=0.47), None, aux)
    assert res.combined_score == 80.0 and [f["source"] for f in res.contributing_factors] == ["aux"]


def test_excluded_sources_reports_only_unreliable_fault():
    assert health_fusion.excluded_sources(None) == []
    assert health_fusion.excluded_sources(_confirmed_fault(input_coverage=None)) == []
    assert health_fusion.excluded_sources(_confirmed_fault(input_coverage=0.9)) == []
    assert health_fusion.excluded_sources(_confirmed_fault(input_coverage=0.47)) == ["fault"]
    # excluded is NOT missing: the fault row exists
    present = health_fusion.missing_sources(_Row(status="VALID"), _confirmed_fault(input_coverage=0.47), _Row(), _Row())
    assert "fault" not in present


# ── schema / API ─────────────────────────────────────────────────────

def _schema(cov):
    return FaultSchema(ts=dt.datetime(2020, 1, 1), engine_id=uuid.uuid4(), model_version_id=uuid.uuid4(), class_id=5,
                       fault_class="Compass Failure", confidence=0.99, probabilities=[0.0] * 7, input_coverage=cov)


def test_schema_computes_reliable_from_coverage():
    assert _schema(0.47).reliable is False
    assert _schema(0.9).reliable is True
    assert _schema(None).reliable is True
    assert _schema(0.47).model_dump()["reliable"] is False  # serialised for the API/UI


async def test_faults_latest_api_exposes_coverage_and_reliability(client, admin_user, make_engine):
    engine = await make_engine()
    async with AsyncSessionLocal() as db:
        db.add(FaultPrediction(ts=dt.datetime(2020, 1, 1, 12), engine_id=engine.id,
                               model_version_id=uuid.UUID("00000000-0000-0000-0000-000000000004"), class_id=5,
                               fault_class="Compass Failure", confidence=0.999, probabilities=[0.0] * 7,
                               state="FAULT_CONFIRMED", input_coverage=fa.input_coverage()))
        await db.commit()
    body = (await client.get(f"/api/v1/engines/{engine.id}/faults/latest", headers=auth_headers(admin_user))).json()
    assert body["input_coverage"] == pytest.approx(15 / 32) and body["reliable"] is False


# ── What-If ──────────────────────────────────────────────────────────

def test_what_if_sets_the_fault_aside_but_still_scores_the_rest():
    rows = make_window()
    res = w.run_scenario("eng-cov", rows, {"cht": rows[-1]["cht"] + 20})
    fault = res["model_results"]["fault"]["scenario"]
    assert fault["status"] == "COMPLETED" and fault["reliable"] is False  # still shown...
    for side in ("baseline", "scenario"):
        fusion = res["health_fusion"][side]
        assert fusion["excluded_sources"] == ["fault"]
        assert "fault" not in fusion["missing_sources"]  # ...and not treated as missing
        assert fusion["sources"]["fault"]["excluded"] is True and fusion["sources"]["fault"]["active"] is False
        assert fusion["forced_zero"] is False
        assert all(f["source"] != "fault" for f in fusion["contributing_factors"])
