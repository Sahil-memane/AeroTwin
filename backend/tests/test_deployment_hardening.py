"""
Tests for the pre-deployment hardening changes:
  * production-safety check for default secrets / wildcard CORS
  * UTF-8 YAML config loading (units like "°C" must not become "Â°C")
  * Health Fusion ignores stale predictions and reports missing sources
  * /health-score flags stale scores
  * throttle / altitude_m are persisted and reach the What-If window
"""
import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.models.fault_prediction import FaultPrediction
from app.models.health_score import HealthScore
from app.models.rul_prediction import RulPrediction
from app.models.telemetry_reading import TelemetryReading
from app.services import health_fusion, what_if_scenario
from app.core.config import settings
from tests.conftest import auth_headers

GOOD = dict(
    DATABASE_URL="postgresql+asyncpg://u:p@h/db",
    JWT_SECRET="x" * 8 + "Zr4kQ9vLw2Pn7Ht5Bd3Ys6Mc1Ja8Ue0G",
    EDGE_API_KEY="Qw3rTy7uIo9pAs5dFg",
    CORS_ORIGINS="https://aerotwin.example.com",
    ENVIRONMENT="production",
)


def _settings(**over):
    return Settings(_env_file=None, **{**GOOD, **over})


# ── production safety ────────────────────────────────────────────────

def test_production_accepts_strong_settings():
    _settings().assert_production_safe()


@pytest.mark.parametrize("over,needle", [
    ({"JWT_SECRET": "local-dev-secret-change-in-production"}, "JWT_SECRET"),
    ({"JWT_SECRET": "short"}, "JWT_SECRET"),
    ({"EDGE_API_KEY": "changeme-edge-api-key"}, "EDGE_API_KEY"),
    ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
    ({"CORS_ORIGINS": "https://a.example.com, *"}, "CORS_ORIGINS"),
])
def test_production_refuses_unsafe_settings(over, needle):
    with pytest.raises(RuntimeError, match=needle):
        _settings(**over).assert_production_safe()


def test_development_allows_defaults():
    _settings(ENVIRONMENT="development", JWT_SECRET="dev", EDGE_API_KEY="changeme", CORS_ORIGINS="*").assert_production_safe()


def test_cors_origins_list_parsing():
    assert _settings(CORS_ORIGINS="https://a.com, https://b.com ,").cors_origins_list == ["https://a.com", "https://b.com"]


# ── YAML encoding ────────────────────────────────────────────────────

def test_what_if_units_are_utf8_not_mojibake():
    units = {p: c["unit"] for p, c in what_if_scenario.parameter_config().items()}
    assert units["cht"] == "°C" and units["egt"] == "°C" and units["oil_temperature"] == "°C"
    assert not any("Â" in u for u in units.values())


# ── missing_sources (pure) ───────────────────────────────────────────

class _Row:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_missing_sources_reports_absent_and_placeholder_rul():
    assert health_fusion.missing_sources(None, None, None, None) == ["rul", "fault", "bearing", "aux"]
    ok = _Row()
    assert health_fusion.missing_sources(ok, ok, ok, ok) == []
    assert health_fusion.missing_sources(_Row(status="MODEL_ERROR"), ok, ok, ok) == ["rul"]


# ── Health Fusion staleness (DB) ─────────────────────────────────────

NOW = dt.datetime(2020, 6, 1, 12, 0, 0)


async def _add(rows):
    async with AsyncSessionLocal() as db:
        db.add_all(rows)
        await db.commit()


def _fault(engine_id, ts):
    return FaultPrediction(
        ts=ts, engine_id=engine_id, model_version_id=uuid.UUID("00000000-0000-0000-0000-000000000004"),
        class_id=5, fault_class="Compass Failure", confidence=0.999, probabilities=[0.0] * 7, state="FAULT_CONFIRMED",
    )


def _rul(engine_id, ts):
    return RulPrediction(
        ts=ts, engine_id=engine_id, model_version_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        rul_cycles=80.0, degradation_index=0.36, rul_lower=60.0, rul_upper=100.0, status="VALID",
    )


async def test_stale_prediction_is_ignored_but_fresh_one_is_used(make_engine):
    engine = await make_engine()
    max_age = settings.HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS
    await _add([
        _fault(engine.id, NOW - dt.timedelta(seconds=max_age + 30)),  # too old
        _rul(engine.id, NOW - dt.timedelta(seconds=1)),               # fresh
    ])
    async with AsyncSessionLocal() as db:
        rul, fault, bearing, aux = await health_fusion.fetch_latest_predictions(db, engine.id, as_of=NOW)
        assert rul is not None and fault is None and bearing is None and aux is None
        # legacy call (no as_of) is unchanged: returns the old row
        _, legacy_fault, _, _ = await health_fusion.fetch_latest_predictions(db, engine.id)
        assert legacy_fault is not None
    assert health_fusion.missing_sources(rul, fault, bearing, aux) == ["fault", "bearing", "aux"]
    # the stale confirmed fault no longer forces the score to zero
    result = health_fusion.compute_health_score(rul, fault, bearing, aux)
    assert not result.forced_zero and result.combined_score > 0


async def test_prediction_from_after_the_reading_is_not_used(make_engine):
    engine = await make_engine()
    await _add([_fault(engine.id, NOW + dt.timedelta(seconds=5))])
    async with AsyncSessionLocal() as db:
        _, fault, _, _ = await health_fusion.fetch_latest_predictions(db, engine.id, as_of=NOW)
    assert fault is None


async def test_fault_just_inside_the_window_is_used(make_engine):
    engine = await make_engine()
    await _add([_fault(engine.id, NOW - dt.timedelta(seconds=settings.HEALTH_FUSION_MAX_PREDICTION_AGE_SECONDS - 1))])
    async with AsyncSessionLocal() as db:
        _, fault, _, _ = await health_fusion.fetch_latest_predictions(db, engine.id, as_of=NOW)
    assert fault is not None


# ── /health-score stale flag ─────────────────────────────────────────

async def test_health_score_endpoint_flags_stale(client, admin_user, make_engine):
    engine = await make_engine()
    old = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(seconds=settings.HEALTH_SCORE_STALE_AFTER_SECONDS + 60)
    await _add([HealthScore(ts=old, engine_id=engine.id, combined_score=72.0, contributing_factors=[])])
    body = (await client.get(f"/api/v1/engines/{engine.id}/health-score", headers=auth_headers(admin_user))).json()
    assert body["stale"] is True and body["combined_score"] == 72.0  # flagged, not hidden
    assert body["age_seconds"] > settings.HEALTH_SCORE_STALE_AFTER_SECONDS

    fresh = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    await _add([HealthScore(ts=fresh, engine_id=engine.id, combined_score=88.0, contributing_factors=[])])
    body = (await client.get(f"/api/v1/engines/{engine.id}/health-score", headers=auth_headers(admin_user))).json()
    assert body["stale"] is False and body["combined_score"] == 88.0


async def test_health_score_endpoint_no_data_is_not_stale(client, admin_user, make_engine):
    engine = await make_engine()
    body = (await client.get(f"/api/v1/engines/{engine.id}/health-score", headers=auth_headers(admin_user))).json()
    assert body["combined_score"] is None and body["stale"] is False and body["age_seconds"] is None


# ── throttle / altitude persistence ──────────────────────────────────

async def test_rest_ingest_persists_throttle_and_altitude(client, make_engine):
    engine = await make_engine()
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    payload = {
        "engine_id": str(engine.id), "ts": ts, "rpm": 3000, "cht": 140, "egt": 700,
        "oil_pressure": 70, "oil_temp": 92, "fuel_flow": 9, "throttle": 0.62, "altitude_m": 1250.0,
    }
    resp = await client.post("/api/v1/telemetry/ingest", json=payload, headers={"X-Edge-Api-Key": settings.EDGE_API_KEY})
    assert resp.status_code == 201, resp.text
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(TelemetryReading).where(TelemetryReading.engine_id == engine.id))).scalars().one()
    assert row.throttle == pytest.approx(0.62) and row.altitude_m == pytest.approx(1250.0)


async def test_rest_ingest_without_them_stores_null_not_zero(client, make_engine):
    engine = await make_engine()
    payload = {
        "engine_id": str(engine.id), "ts": dt.datetime.now(dt.timezone.utc).isoformat(), "rpm": 3000, "cht": 140,
        "egt": 700, "oil_pressure": 70, "oil_temp": 92, "fuel_flow": 9,
    }
    assert (await client.post("/api/v1/telemetry/ingest", json=payload, headers={"X-Edge-Api-Key": settings.EDGE_API_KEY})).status_code == 201
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(TelemetryReading).where(TelemetryReading.engine_id == engine.id))).scalars().one()
    assert row.throttle is None and row.altitude_m is None


async def test_what_if_window_carries_throttle_and_altitude(client, admin_user, make_engine, monkeypatch):
    engine = await make_engine()
    base = dt.datetime(2020, 1, 1, 12, 0, 0)
    await _add([
        TelemetryReading(engine_id=engine.id, ts=base + dt.timedelta(seconds=i), rpm=3000, cht=140, egt=700,
                         oil_pressure=70, oil_temp=92, fuel_flow=9, throttle=0.6, altitude_m=900.0 if i % 2 else None)
        for i in range(5)
    ])
    seen = {}

    def fake_run(engine_id, rows, params):
        seen["rows"] = rows
        return {"simulation_status": "COMPLETED"}

    monkeypatch.setattr(what_if_scenario, "run_scenario", fake_run)
    resp = await client.post("/api/v1/simulation/what-if", headers=auth_headers(admin_user),
                             json={"engine_id": str(engine.id), "parameters": {"cht": 150}})
    assert resp.status_code == 200
    assert [r["throttle"] for r in seen["rows"]] == [0.6] * 5
    assert [r["altitude_m"] for r in seen["rows"]] == [None, 900.0, None, 900.0, None]

    # and _prepare forwards real values while dropping missing ones (no invented zero)
    p = what_if_scenario._prepare(seen["rows"][1])
    assert p["throttle"] == 0.6 and p["altitude_m"] == 900.0
    assert "altitude_m" not in what_if_scenario._prepare(seen["rows"][0])
