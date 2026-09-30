"""
Tests for the simulation API — validation rules and the what-if path
(fast: a few dozen synthetic points). Replay is exercised manually
against real data (see the plan) since a full run against thousands of
stored readings takes real wall-clock time unsuitable for a unit test.
"""
import asyncio
import uuid

from tests.conftest import auth_headers


async def test_what_if_requires_environmental_profile_not_mission_id(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        "/api/v1/simulation/run",
        json={"engine_id": str(engine.id), "mode": "what_if", "mission_id": str(uuid.uuid4())},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 400


async def test_replay_requires_mission_id_not_environmental_profile(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        "/api/v1/simulation/run",
        json={"engine_id": str(engine.id), "mode": "replay", "environmental_profile": {"altitude_m": 1000}},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 400


async def test_run_unknown_engine_404(client, admin_user):
    resp = await client.post(
        "/api/v1/simulation/run",
        json={"engine_id": str(uuid.uuid4()), "mode": "what_if", "environmental_profile": {"altitude_m": 1000}},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 404


async def test_replay_unknown_mission_404(client, admin_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        "/api/v1/simulation/run",
        json={"engine_id": str(engine.id), "mode": "replay", "mission_id": str(uuid.uuid4())},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 404


async def test_run_requires_privileged_role(client, operator_user, make_engine):
    engine = await make_engine()
    resp = await client.post(
        "/api/v1/simulation/run",
        json={"engine_id": str(engine.id), "mode": "what_if", "environmental_profile": {"altitude_m": 1000}},
        headers=auth_headers(operator_user),
    )
    assert resp.status_code == 403


async def test_get_unknown_simulation_404(client, admin_user):
    resp = await client.get(f"/api/v1/simulation/{uuid.uuid4()}", headers=auth_headers(admin_user))
    assert resp.status_code == 404


async def test_what_if_run_completes_with_real_health_scores(client, admin_user, make_engine):
    engine = await make_engine()
    create = await client.post(
        "/api/v1/simulation/run",
        json={
            "engine_id": str(engine.id),
            "mode": "what_if",
            "environmental_profile": {"preset": "nominal_cruise"},
        },
        headers=auth_headers(admin_user),
    )
    assert create.status_code == 202
    simulation_id = create.json()["simulation_id"]
    assert create.json()["status"] == "queued"

    # Poll generously: the 42-point run itself is fast, but the first
    # call in a fresh process pays real cold-start cost lazy-loading the
    # sklearn/lightgbm/TensorFlow model artifacts from disk.
    for _ in range(60):
        await asyncio.sleep(1.0)
        poll = await client.get(f"/api/v1/simulation/{simulation_id}", headers=auth_headers(admin_user))
        if poll.json()["status"] in ("completed", "failed"):
            break

    body = poll.json()
    assert body["status"] == "completed", body.get("error")
    assert len(body["results"]) == 42
    assert "combined_score" in body["results"][0]["health_score"]
