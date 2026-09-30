"""
Tests for the Alert Engine: severity thresholds, cooldown suppression,
and the escalation-bypasses-cooldown rule.
"""
from datetime import datetime, timedelta

import pytest

from app.services import alert_engine
from app.services.health_fusion import HealthScoreResult
from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _reset_alert_engine_state():
    """`_last_alert` is process-global by design (see alert_engine.py's
    docstring) — tests must not leak cooldown state into each other."""
    alert_engine._last_alert.clear()
    yield
    alert_engine._last_alert.clear()


def _result(score, forced_zero=False):
    return HealthScoreResult(combined_score=score, contributing_factors=[], forced_zero=forced_zero)


# ── Pure severity-threshold tests ──────────────────────────────────────

def test_severity_boundary_healthy_at_50():
    assert alert_engine._severity_for(_result(50.0)) is None


def test_severity_boundary_warning_just_under_50():
    assert alert_engine._severity_for(_result(49.9)) == "warning"


def test_severity_boundary_warning_at_20():
    assert alert_engine._severity_for(_result(20.0)) == "warning"


def test_severity_boundary_critical_just_under_20():
    assert alert_engine._severity_for(_result(19.9)) == "critical"


def test_severity_forced_zero_is_always_critical():
    assert alert_engine._severity_for(_result(0.0, forced_zero=True)) == "critical"


# ── Cooldown logic (pure, in-memory) ───────────────────────────────────

def test_should_fire_true_when_no_prior_alert():
    assert alert_engine._should_fire("engine-1", "warning", datetime(2026, 1, 1, 12, 0, 0))


def test_should_fire_false_within_cooldown_same_severity():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert_engine._last_alert["engine-1"] = ("warning", now)
    later = now + timedelta(minutes=2)  # within the 5-minute default cooldown
    assert not alert_engine._should_fire("engine-1", "warning", later)


def test_should_fire_true_after_cooldown_elapses():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert_engine._last_alert["engine-1"] = ("warning", now)
    later = now + timedelta(minutes=6)
    assert alert_engine._should_fire("engine-1", "warning", later)


def test_should_fire_true_on_escalation_even_inside_cooldown():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert_engine._last_alert["engine-1"] = ("warning", now)
    moments_later = now + timedelta(seconds=1)
    assert alert_engine._should_fire("engine-1", "critical", moments_later)


def test_should_fire_false_for_deescalation_inside_cooldown():
    now = datetime(2026, 1, 1, 12, 0, 0)
    alert_engine._last_alert["engine-1"] = ("critical", now)
    moments_later = now + timedelta(seconds=1)
    assert not alert_engine._should_fire("engine-1", "warning", moments_later)


# ── Integration: evaluate_and_alert persists + respects cooldown ──────

async def test_evaluate_and_alert_persists_and_suppresses_duplicates(make_engine):
    engine = await make_engine()
    ts1 = datetime(2026, 1, 1, 12, 0, 0)

    async with AsyncSessionLocal() as session:
        first = await alert_engine.evaluate_and_alert(session, engine.id, ts1, _result(10.0))
    assert first is not None
    assert first.severity == "critical"

    ts2 = ts1 + timedelta(minutes=1)  # inside the 5-minute cooldown, same severity
    async with AsyncSessionLocal() as session:
        second = await alert_engine.evaluate_and_alert(session, engine.id, ts2, _result(10.0))
    assert second is None

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Alert).where(Alert.engine_id == engine.id))
        assert len(result.scalars().all()) == 1


async def test_evaluate_and_alert_concurrent_calls_fire_only_once(make_engine):
    """Regression: a burst of near-simultaneous _handle_message coroutines
    for the same engine (as MQTT can deliver) must not all pass the
    cooldown check before any of them updates it."""
    import asyncio

    engine = await make_engine()
    ts = datetime(2026, 1, 1, 12, 0, 0)

    async def fire():
        async with AsyncSessionLocal() as session:
            return await alert_engine.evaluate_and_alert(session, engine.id, ts, _result(10.0))

    results = await asyncio.gather(*[fire() for _ in range(10)])
    fired = [r for r in results if r is not None]
    assert len(fired) == 1

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Alert).where(Alert.engine_id == engine.id))
        assert len(result.scalars().all()) == 1


async def test_evaluate_and_alert_healthy_score_fires_nothing(make_engine):
    engine = await make_engine()
    async with AsyncSessionLocal() as session:
        result = await alert_engine.evaluate_and_alert(
            session, engine.id, datetime(2026, 1, 1, 12, 0, 0), _result(95.0)
        )
    assert result is None
