"""
Tests for the What-If parameter-perturbation engine (app/services/what_if_scenario.py)
and its API (`POST /simulation/what-if`).

Service-level tests run the REAL RUL/Fault/Bearing/Aux models over a
deterministic synthetic cruise window (no database). API-level tests seed a
throwaway engine's telemetry in the dev Postgres (same convention as the
rest of the suite — see conftest.py) and assert the request is strictly
read-only.

Documented numerical tolerance for "no change" comparisons: 1e-9 (relative
and absolute; `w.CHANGE_TOLERANCE`, the same threshold the service uses to
decide a model output "changed"). The bearing RNG is seeded from window
identity, and RUL/Fault/Bearing reproduce bit-for-bit, but the auxiliary
sklearn model was observed to differ by ~1e-14 between identical runs when
the machine is loaded (multithreaded reduction order) — so exact equality
would be a flaky claim. Everything discrete (classes, states, statuses,
factor lists) is still compared exactly.
"""
import copy
import datetime as dt
import math
import os
import sys
import uuid

import pytest
from sqlalchemy import func, select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.aux_prediction import AuxPrediction
from app.models.bearing_health_reading import BearingHealthReading
from app.models.fault_prediction import FaultPrediction
from app.models.health_score import HealthScore
from app.models.rul_prediction import RulPrediction
from app.models.telemetry_reading import TelemetryReading
from app.services import alert_engine, what_if_scenario as w
from app.services.aux_adapter import aux_adapter
from app.services.fault_adapter import piston_to_uav_telemetry
from app.services.fault_service import fault_service
from app.services.fault_state import fault_state_machine
from app.services.physics_ingestion import compute_consistency
from app.services.rul_adapter import piston_to_cmapss
from app.services.rul_service import rul_service
from tests.conftest import auth_headers

FIELDS = {"rpm": "rpm", "cht": "cht", "egt": "egt", "oil_pressure": "oil_pressure",
          "oil_temperature": "oil_temp", "fuel_flow": "fuel_flow"}
T0 = dt.datetime(2020, 1, 1, 12, 0, 0)


def make_window(n: int | None = None) -> list[dict]:
    """Deterministic cruise-like window (oldest -> newest) with small,
    reproducible variation so window statistics are non-degenerate."""
    n = n if n is not None else w.required_window_size()
    rows = []
    for i in range(n):
        wig = math.sin(i * 0.9)
        rows.append({
            "ts": T0 + dt.timedelta(seconds=2 * i),
            "rpm": 4800.0 + 40 * wig,
            "cht": 150.0 + 2 * wig,
            "egt": 830.0 + 6 * wig,
            "oil_pressure": 90.0 + 1.5 * wig,
            "oil_temp": 98.0 + 1.0 * wig,
            "fuel_flow": 8.5 + 0.2 * wig,
            "vibration_x": 0.3 + 0.05 * wig,
            "vibration_y": 0.24 + 0.04 * wig,
            "vibration_z": 0.18 + 0.03 * wig,
        })
    return rows


@pytest.fixture(scope="module")
def window() -> list[dict]:
    return make_window()


@pytest.fixture(scope="module")
def baseline_result(window):
    """A no-change run, shared across tests (models are deterministic)."""
    last = window[-1]
    return w.run_scenario("eng-test", window, {"rpm": last["rpm"]})


def same(a, b):
    """Deep equality: discrete values exactly, floats within 1e-9."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == pytest.approx(b, rel=w.CHANGE_TOLERANCE, abs=w.CHANGE_TOLERANCE)
    return a == b


def _live_state_snapshot():
    return (
        dict(rul_service._windows),
        dict(fault_service._windows),
        dict(fault_service._prev_vibes),
        dict(fault_state_machine._trackers),
        dict(aux_adapter._wear_state),
    )


def _sig(snapshot):
    return tuple(sorted(d.keys()) if isinstance(d, dict) else d for d in snapshot)


# ── Configuration ────────────────────────────────────────────────────

def test_k_comes_from_configuration_and_window_size_derives_from_it():
    assert w.PERTURBATION_WINDOW == 10
    assert w.required_window_size() == fault_service.window_len - 1 + w.PERTURBATION_WINDOW


def test_parameter_config_bounds_come_from_sensor_bounds():
    from app.services.validation import SENSOR_BOUNDS
    cfg = w.parameter_config()
    assert set(cfg) == set(FIELDS)
    for name, field in FIELDS.items():
        assert (cfg[name]["min"], cfg[name]["max"]) == tuple(SENSOR_BOUNDS[field])
        assert cfg[name]["step"] > 0 and cfg[name]["unit"]


# ── Validation ───────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {}, None, [], {"rpm": float("nan")}, {"rpm": float("inf")}, {"rpm": -float("inf")},
    {"rpm": None}, {"rpm": "5000"}, {"rpm": True}, {"rpm": -1}, {"rpm": 999999},
    {"cht": 401}, {"oil_pressure": -0.1}, {"fuel_flow": 31}, {"bogus": 1}, {"rpm": 5000, "egt": 5000},
])
def test_invalid_parameters_rejected(bad):
    clean, errors = w.validate_parameters(bad)
    assert errors, f"{bad!r} should be rejected"


def test_valid_parameters_accepted_and_omitted_means_unchanged():
    clean, errors = w.validate_parameters({"rpm": 5000, "oil_temperature": 100.5})
    assert not errors and clean == {"rpm": 5000.0, "oil_temperature": 100.5}


# ── No-change scenario (the critical consistency test) ───────────────

def test_no_change_scenario_is_exact_noop(window, baseline_result):
    res = baseline_result
    assert res["simulation_status"] == "COMPLETED"
    assert all(v == 0 for v in res["delta"].values())
    assert res["baseline"] == res["scenario"]  # exact: scenario values are the baseline values
    for name, block in res["model_results"].items():
        assert block["changed"] is False, name
        assert same(block["baseline"], block["scenario"]), name
    hf = res["health_fusion"]
    assert same(hf["baseline"]["score"], hf["scenario"]["score"])
    assert hf["score_delta"] == 0
    assert same(hf["baseline"]["contributing_factors"], hf["scenario"]["contributing_factors"])
    assert res["alerts"]["change"] in ("NONE", "UNCHANGED")
    pc = res["physics_consistency"]
    assert same(pc["deviation_score"]["baseline"], pc["deviation_score"]["scenario"])
    for p in pc["parameters"].values():
        assert p["residual"] == p["baseline_residual"] and p["status"] == p["baseline_status"]


def test_full_explicit_no_change_equals_partial_no_change(window, baseline_result):
    last = window[-1]
    full = {p: last[f] for p, f in FIELDS.items()}
    res = w.run_scenario("eng-test", window, full)
    assert all(v == 0 for v in res["delta"].values())
    assert same(res["model_results"]["fault"]["scenario"], baseline_result["model_results"]["fault"]["scenario"])
    assert same(res["health_fusion"]["scenario"]["score"], baseline_result["health_fusion"]["scenario"]["score"])


def test_bearing_inference_is_deterministic_across_runs(window, baseline_result):
    again = w.run_scenario("eng-test", window, {"rpm": window[-1]["rpm"]})
    assert same(again["model_results"]["bearing"]["scenario"], baseline_result["model_results"]["bearing"]["scenario"])


def test_bearing_seed_depends_on_window_identity_not_scenario_values():
    assert w._bearing_seed("e", "t") == w._bearing_seed("e", "t")
    assert w._bearing_seed("e", "t") != w._bearing_seed("e", "t2")


# ── Single-parameter scenarios ───────────────────────────────────────

SINGLE = [
    ("rpm", +400.0), ("cht", +25.0), ("egt", +60.0),
    ("oil_pressure", -25.0), ("oil_temperature", +20.0), ("fuel_flow", +2.0),
]


@pytest.mark.parametrize("param,shift", SINGLE)
def test_single_parameter_change(window, baseline_result, param, shift):
    base_before = copy.deepcopy(window)
    last = window[-1][FIELDS[param]]
    res = w.run_scenario("eng-test", window, {param: last + shift})

    assert window == base_before, "input rows must never be mutated"
    assert res["simulation_status"] == "COMPLETED"
    assert res["delta"][param] == pytest.approx(shift)
    assert res["scenario"][param] == pytest.approx(last + shift)
    for other in FIELDS:
        if other != param:
            assert res["delta"][other] == 0 and res["scenario"][other] == res["baseline"][other]
    assert res["window"]["perturbed_readings"] == w.PERTURBATION_WINDOW
    assert res["scenario_type"] == "PARAMETER_PERTURBATION" and res["mode"] == "WHAT_IF"

    # bearing/aux honestly report whether their inputs were touched
    assert res["model_results"]["bearing"]["input_changed"] is (param == "rpm")
    assert res["model_results"]["auxiliary"]["input_changed"] is (param in ("rpm", "cht"))
    if param != "rpm":
        assert res["model_results"]["bearing"]["changed"] is False
        assert "unchanged" in res["model_results"]["bearing"]["note"].lower()
    if param not in ("rpm", "cht"):
        aux = res["model_results"]["auxiliary"]
        assert aux["changed"] is False and same(aux["baseline"], aux["scenario"])

    # every scenario is compared to the same baseline as the no-change run
    assert same(res["model_results"]["rul"]["baseline"], baseline_result["model_results"]["rul"]["baseline"])
    assert same(res["health_fusion"]["baseline"]["score"], baseline_result["health_fusion"]["baseline"]["score"])


def test_perturbation_is_delta_on_last_k_only():
    rows = make_window()
    out, clamped = w.apply_perturbation(rows, {"egt": rows[-1]["egt"] + 50}, 10)
    assert clamped == 0
    assert out[-1]["egt"] == pytest.approx(rows[-1]["egt"] + 50)
    for i, (a, b) in enumerate(zip(rows, out)):
        if i >= len(rows) - 10:
            assert b["egt"] == pytest.approx(a["egt"] + 50)
        else:
            assert b == a
        assert b["rpm"] == a["rpm"]  # other channels untouched


def test_perturbation_clamps_and_reports_out_of_bounds_shift():
    rows = make_window()
    out, clamped = w.apply_perturbation(rows, {"cht": 400.0}, 10)  # huge shift up
    assert out[-1]["cht"] == 400.0
    assert all(r["cht"] <= 400.0 for r in out)
    assert clamped >= 0


def test_combined_scenario_reaches_the_models(window, baseline_result):
    last = window[-1]
    res = w.run_scenario("eng-test", window, {
        "rpm": last["rpm"] + 500, "egt": last["egt"] + 70,
        "oil_pressure": last["oil_pressure"] - 30, "fuel_flow": last["fuel_flow"] + 3,
    })
    assert res["simulation_status"] == "COMPLETED"
    assert res["delta"]["cht"] == 0 and res["delta"]["oil_temperature"] == 0
    m = res["model_results"]
    # The perturbed window must be different model input, so at least one
    # real model output moves — not merely echoed baseline values.
    assert any(m[k]["changed"] for k in m)


# ── Feature mapping is verified against the real adapters ────────────

@pytest.mark.parametrize("param", list(FIELDS))
def test_declared_feature_mapping_matches_adapters(param):
    field = FIELDS[param]
    row = make_window()[-1]
    data = w._prepare(row)
    bumped = dict(data)
    bumped[field] = data[field] + 5.0

    rul_changes = piston_to_cmapss(data) != piston_to_cmapss(bumped)
    fault_changes = list(piston_to_uav_telemetry(data)) != list(piston_to_uav_telemetry(bumped))
    aux_changes = not (
        aux_adapter.raw_to_engineered_features(aux_adapter.telemetry_to_raw_features("map-a", data)).tolist()
        == aux_adapter.raw_to_engineered_features(aux_adapter.telemetry_to_raw_features("map-b", bumped)).tolist()
    )
    aux_adapter.reset_engine("map-a"); aux_adapter.reset_engine("map-b")

    declared = w.FEATURE_MAPPING
    assert rul_changes == (param in declared["rul"]["direct"])
    assert fault_changes == (param in declared["fault"]["direct"])
    assert aux_changes == (param in declared["auxiliary"]["direct"])
    # bearing: model input is (vibration_magnitude, rpm) only
    assert (param == "rpm") == (param in declared["bearing"]["direct"])
    assert data["vibration_magnitude"] == w._prepare(bumped)["vibration_magnitude"]


# ── deviation_score ──────────────────────────────────────────────────

def test_prepare_uses_server_side_physics_deviation_not_zero():
    row = make_window()[-1]
    row_bad = {**row, "cht": 260.0, "egt": 500.0}  # far from physics expectation
    d_ok, d_bad = w._prepare(row)["deviation_score"], w._prepare(row_bad)["deviation_score"]
    assert d_ok == compute_consistency({k: v for k, v in row.items() if v is not None})[0]
    assert d_bad > d_ok > 0


def test_deviation_score_reaches_rul_features():
    data = w._prepare(make_window()[-1])
    assert piston_to_cmapss({**data, "deviation_score": 0.0}) != piston_to_cmapss(data)


def test_replay_engine_now_computes_deviation_score(monkeypatch):
    """The shared run_sequence path (replay + preset what-if) previously
    left deviation_score unset (RUL saw 0)."""
    from simulation import replay_engine
    seen = []
    monkeypatch.setattr(replay_engine, "piston_to_cmapss", lambda d: seen.append(d.get("deviation_score")) or (_ for _ in ()).throw(RuntimeError("stop")))
    rows = [{k: v for k, v in r.items() if k != "ts"} for r in make_window(3)]
    replay_engine.run_sequence(rows, "dev-score-test")
    assert seen and all(isinstance(s, float) and s > 0 for s in seen)


# ── Insufficient history ─────────────────────────────────────────────

def test_insufficient_history_never_becomes_rul_zero():
    rows = make_window(20)
    res = w.run_scenario("eng-test", rows, {"cht": rows[-1]["cht"] + 20})
    assert res["simulation_status"] == "INSUFFICIENT_DATA"
    assert res["window"]["data_sufficiency"] == "INSUFFICIENT_DATA"
    rul = res["model_results"]["rul"]["scenario"]
    assert rul["status"] == "INSUFFICIENT_DATA" and "rul_cycles" not in rul
    assert res["model_results"]["fault"]["scenario"]["status"] == "INSUFFICIENT_DATA"
    assert set(res["health_fusion"]["scenario"]["missing_sources"]) >= {"rul", "fault"}


def test_partial_history_runs_rul_but_not_fault():
    rows = make_window(50)
    res = w.run_scenario("eng-test", rows, {"cht": rows[-1]["cht"] + 20})
    assert res["window"]["data_sufficiency"] == "PARTIAL"
    assert res["model_results"]["rul"]["scenario"]["status"] == "COMPLETED"
    assert res["model_results"]["fault"]["scenario"]["status"] == "INSUFFICIENT_DATA"
    assert res["simulation_status"] == "INSUFFICIENT_DATA"


def test_no_telemetry_reports_unavailable_not_fake_values():
    res = w.run_scenario("eng-test", [], {"rpm": 5000.0})
    assert res["simulation_status"] == "INSUFFICIENT_DATA"
    assert res["baseline"] is None and res["model_results"] is None


# ── Health Fusion / alerts / physics views ───────────────────────────

def test_health_fusion_exposes_all_four_sources(baseline_result):
    for side in ("baseline", "scenario"):
        src = baseline_result["health_fusion"][side]["sources"]
        assert set(src) == {"rul", "fault", "bearing", "aux"}
        for s in src.values():
            assert set(s) == {"penalty", "active", "forced_zero", "available", "excluded"}
            assert s["penalty"] is None or s["penalty"] >= 0
        for f in baseline_result["health_fusion"][side]["contributing_factors"]:
            assert src[f["source"]]["active"] is True


def test_physics_consistency_shape_and_semantics(window):
    last = window[-1]
    res = w.run_scenario("eng-test", window, {"cht": last["cht"] + 30})
    params = res["physics_consistency"]["parameters"]
    assert set(params) == {"cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"}  # no rpm
    for name, p in params.items():
        assert set(p) >= {"expected", "measured", "residual", "status", "method"}
    assert params["cht"]["measured"] == pytest.approx(last["cht"] + 30, abs=0.01)
    # expected CHT is independent of measured CHT, so the residual moves by exactly the delta
    assert params["cht"]["residual"] - params["cht"]["baseline_residual"] == pytest.approx(30, abs=0.02)
    assert params["egt"]["residual"] == params["egt"]["baseline_residual"]


def test_simulation_alerts_use_production_rules_and_are_flagged(window):
    from app.services.health_fusion import HealthScoreResult
    crit = HealthScoreResult(combined_score=10.0, contributing_factors=[], forced_zero=False)
    warn = HealthScoreResult(combined_score=40.0, contributing_factors=[], forced_zero=False)
    ok = HealthScoreResult(combined_score=90.0, contributing_factors=[])
    assert alert_engine.describe_alert(crit)["severity"] == alert_engine._severity_for(crit) == "critical"
    assert alert_engine.describe_alert(warn)["severity"] == alert_engine._severity_for(warn) == "warning"
    assert alert_engine.describe_alert(ok) is None
    assert alert_engine.describe_alert(warn)["message"] == alert_engine._build_message([])
    v = w._alerts_view(ok, crit)
    assert v["change"] == "NEW" and v["scenario"]["simulation"] is True and v["simulation"] is True
    assert w._alerts_view(crit, ok)["change"] == "CLEARED"
    assert w._alerts_view(warn, crit)["change"] == "ESCALATED"
    assert w._alerts_view(warn, warn)["change"] == "UNCHANGED"


# ── Isolation / reset ────────────────────────────────────────────────

def test_run_leaves_no_state_in_model_services(window):
    before = _sig(_live_state_snapshot())
    last = window[-1]
    w.run_scenario("eng-live", window, {"rpm": last["rpm"] + 300, "cht": last["cht"] + 20})
    assert _sig(_live_state_snapshot()) == before
    assert "eng-live" not in aux_adapter._wear_state


def test_scenario_does_not_call_alert_engine_or_touch_cooldown(window, monkeypatch):
    calls = []

    async def boom(*a, **k):
        calls.append(1)
        raise AssertionError("evaluate_and_alert must not be called by What-If")

    monkeypatch.setattr(alert_engine, "evaluate_and_alert", boom)
    cooldown_before = dict(alert_engine._last_alert)
    last = window[-1]
    w.run_scenario("eng-test", window, {"egt": last["egt"] + 100, "oil_pressure": last["oil_pressure"] - 50})
    assert not calls and alert_engine._last_alert == cooldown_before


def test_reset_scenario_returns_to_baseline_and_is_stateless(window, baseline_result):
    """"Reset to current" == submitting the current values. After an
    intervening large scenario, the reset run must equal the original
    baseline run exactly (no leaked state)."""
    last = window[-1]
    w.run_scenario("eng-test", window, {p: last[f] + 10 for p, f in FIELDS.items()})
    reset = w.run_scenario("eng-test", window, {p: last[f] for p, f in FIELDS.items()})
    assert all(v == 0 for v in reset["delta"].values())
    assert same(reset["model_results"]["fault"]["scenario"], baseline_result["model_results"]["fault"]["scenario"])
    assert same(reset["health_fusion"]["scenario"]["score"], baseline_result["health_fusion"]["scenario"]["score"])


def test_aux_wear_seeded_from_live_state_and_restored(window):
    aux_adapter.set_wear("eng-wear", 100.0)
    try:
        res = w.run_scenario("eng-wear", window, {"rpm": window[-1]["rpm"]})
        assert res["window"]["aux_wear_source"] == "live_state"
        used = sum(aux_adapter.wear_increment(r["rpm"]) for r in window)
        assert res["window"]["aux_wear_seed"] == pytest.approx(100.0 - used, abs=1e-5)
        assert aux_adapter.get_wear("eng-wear") == 100.0  # live value untouched
    finally:
        aux_adapter.reset_engine("eng-wear")


# ── API level (DB-backed) ────────────────────────────────────────────

async def _seed_readings(engine_id, rows):
    async with AsyncSessionLocal() as db:
        db.add_all([TelemetryReading(engine_id=engine_id, **r) for r in rows])
        await db.commit()


async def _counts(engine_id):
    out = {}
    async with AsyncSessionLocal() as db:
        for model in (TelemetryReading, Alert, HealthScore, RulPrediction, FaultPrediction, AuxPrediction, BearingHealthReading):
            out[model.__tablename__] = (await db.execute(
                select(func.count()).select_from(model).where(model.engine_id == engine_id))).scalar_one()
    return out


async def _telemetry_rows(engine_id):
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(TelemetryReading).where(TelemetryReading.engine_id == engine_id)
                                 .order_by(TelemetryReading.ts))).scalars().all()
    return [(r.ts, r.rpm, r.cht, r.egt, r.oil_pressure, r.oil_temp, r.fuel_flow) for r in rows]


async def test_api_what_if_is_read_only_and_broadcasts_nothing(client, admin_user, make_engine, monkeypatch):
    engine = await make_engine()
    await _seed_readings(engine.id, make_window())
    before_rows, before_counts = await _telemetry_rows(engine.id), await _counts(engine.id)

    broadcasts = []

    async def record(*a, **k):
        broadcasts.append((a, k))

    from app.ws.connection_manager import manager
    monkeypatch.setattr(manager, "broadcast_to_engine", record)
    cooldown_before = dict(alert_engine._last_alert)

    last = make_window()[-1]
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user), json={
        "engine_id": str(engine.id),
        "parameters": {"rpm": last["rpm"] + 600, "egt": last["egt"] + 80, "oil_pressure": last["oil_pressure"] - 30},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_status"] == "COMPLETED"
    assert body["mode"] == "WHAT_IF" and body["scenario_type"] == "PARAMETER_PERTURBATION"
    assert body["perturbation_count"] == w.PERTURBATION_WINDOW
    assert body["window"]["total_readings"] == w.required_window_size()
    assert body["window"]["data_sufficiency"] == "SUFFICIENT"
    assert set(body["model_versions"]) == {"rul_model", "fault_model", "bearing_model", "aux_model"}
    assert body["baseline_timestamp"] == make_window()[-1]["ts"].isoformat()
    assert body["delta"]["rpm"] == pytest.approx(600)
    assert set(body["physics_consistency"]["parameters"]) == {"cht", "egt", "oil_pressure", "oil_temperature", "fuel_flow"}
    assert body["alerts"]["simulation"] is True

    # isolation: telemetry, predictions, scores, alerts unchanged; nothing broadcast
    assert await _telemetry_rows(engine.id) == before_rows
    assert await _counts(engine.id) == before_counts
    assert before_counts["alerts"] == 0
    assert broadcasts == []
    assert alert_engine._last_alert == cooldown_before


async def test_api_no_change_scenario_matches_baseline(client, admin_user, make_engine):
    engine = await make_engine()
    rows = make_window()
    await _seed_readings(engine.id, rows)
    last = rows[-1]
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user), json={
        "engine_id": str(engine.id), "parameters": {p: last[f] for p, f in FIELDS.items()}})
    body = resp.json()
    assert resp.status_code == 200 and all(v == 0 for v in body["delta"].values())
    assert body["health_fusion"]["score_delta"] == 0
    assert all(not b["changed"] for b in body["model_results"].values())


async def test_api_baseline_timestamp_pins_window(client, admin_user, make_engine):
    engine = await make_engine()
    rows = make_window(w.required_window_size() + 20)
    await _seed_readings(engine.id, rows)
    pin = rows[-11]["ts"]
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user), json={
        "engine_id": str(engine.id), "baseline_timestamp": pin.isoformat() + "Z",
        "parameters": {"cht": 160}})
    body = resp.json()
    assert resp.status_code == 200
    assert body["baseline_timestamp"] == pin.isoformat()
    assert body["baseline"]["cht"] == rows[-11]["cht"]


async def test_api_insufficient_history(client, admin_user, make_engine):
    engine = await make_engine()
    await _seed_readings(engine.id, make_window(15))
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user),
                             json={"engine_id": str(engine.id), "parameters": {"cht": 160}})
    body = resp.json()
    assert resp.status_code == 200 and body["simulation_status"] == "INSUFFICIENT_DATA"
    assert body["model_results"]["rul"]["scenario"]["status"] == "INSUFFICIENT_DATA"
    assert "rul_cycles" not in body["model_results"]["rul"]["scenario"]


async def test_api_engine_with_no_telemetry(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user),
                             json={"engine_id": str(engine.id), "parameters": {"cht": 160}})
    body = resp.json()
    assert resp.status_code == 200 and body["simulation_status"] == "INSUFFICIENT_DATA" and body["baseline"] is None


@pytest.mark.parametrize("params", [
    {"rpm": 999999}, {"cht": -5}, {"rpm": None}, {"rpm": "fast"}, {"nope": 1}, {},
])
async def test_api_invalid_input_rejected_without_running(client, admin_user, make_engine, params):
    engine = await make_engine()
    await _seed_readings(engine.id, make_window(5))
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user),
                             json={"engine_id": str(engine.id), "parameters": params})
    assert resp.status_code == 400
    assert resp.json()["detail"]["simulation_status"] == "INVALID_INPUT"


async def test_api_rejects_nan_and_infinity_literals(client, admin_user, make_engine):
    engine = await make_engine()
    for lit in ("NaN", "Infinity", "-Infinity"):
        resp = await client.post(
            "/api/v1/simulation/what-if", headers={**auth_headers(admin_user), "Content-Type": "application/json"},
            content=f'{{"engine_id": "{engine.id}", "parameters": {{"rpm": {lit}}}}}')
        assert resp.status_code == 400, lit


async def test_api_unknown_engine_404_and_role_check(client, admin_user, operator_user, make_engine):
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user),
                             json={"engine_id": str(uuid.uuid4()), "parameters": {"rpm": 3000}})
    assert resp.status_code == 404
    engine = await make_engine()
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(operator_user),
                             json={"engine_id": str(engine.id), "parameters": {"rpm": 3000}})
    assert resp.status_code == 403


async def test_api_config_endpoint(client, admin_user):
    resp = await client.get("/api/v1/simulation/what-if/config", headers=auth_headers(admin_user))
    body = resp.json()
    assert resp.status_code == 200
    assert set(body["parameters"]) == set(FIELDS)
    assert body["perturbation_window"] == w.PERTURBATION_WINDOW
    assert body["required_readings"] == {"fault": fault_service.window_len, "rul": rul_service.window_len}


async def test_replay_and_preset_what_if_unaffected_by_scenario_endpoint(client, admin_user, make_engine):
    """Replay/preset routes still validate exactly as before (mode isolation)."""
    engine = await make_engine()
    resp = await client.post("/api/v1/simulation/run", headers=auth_headers(admin_user),
                             json={"engine_id": str(engine.id), "mode": "what_if", "mission_id": str(uuid.uuid4())})
    assert resp.status_code == 400
