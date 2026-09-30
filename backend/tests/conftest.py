"""
Shared pytest fixtures for API-level tests.

There is no separate test database configured for this project (a
hackathon-scoped decision — see the Implementation Document's testing
strategy, which assumes "a test DB container" but none is wired up).
These fixtures instead run against the same dev Postgres the app already
uses (DATABASE_URL from `.env`), creating throwaway rows per test and
deleting them in teardown, rather than standing up a second database.
"""
import os
import sys
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.db.session import AsyncSessionLocal
from app.core.security import get_password_hash, create_access_token
from app.models.user import User
from app.models.uav_asset import UAVAsset
from app.models.engine import Engine
from app.models.mission import Mission
from app.models.alert import Alert
from app.models.maintenance_log import MaintenanceLog
from app.models.telemetry_reading import TelemetryReading
from app.models.rul_prediction import RulPrediction
from app.models.fault_prediction import FaultPrediction
from app.models.aux_prediction import AuxPrediction
from app.models.bearing_health_reading import BearingHealthReading
from app.models.health_score import HealthScore
from app.models.simulation_run import SimulationRun
from app.api.v1.auth import limiter as auth_login_limiter
from sqlalchemy import delete


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Prevent the login/refresh rate limiter's in-memory state from
    leaking between tests (all tests share one process/IP)."""
    auth_login_limiter.reset()
    yield
    auth_login_limiter.reset()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


TEST_PASSWORD = "TestPass123!"


@pytest_asyncio.fixture
async def make_user():
    """Factory fixture: create a test user with a given role, clean it up after the test."""
    created_ids = []

    async def _make(role: str, is_active: bool = True) -> User:
        async with AsyncSessionLocal() as db:
            user = User(
                id=uuid.uuid4(),
                email=f"{role}-{uuid.uuid4().hex[:8]}@test.aerotwin",
                hashed_password=get_password_hash(TEST_PASSWORD),
                role=role,
                is_active=is_active,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            created_ids.append(user.id)
            return user

    yield _make

    async with AsyncSessionLocal() as db:
        for user_id in created_ids:
            existing = await db.get(User, user_id)
            if existing:
                await db.delete(existing)
        await db.commit()


@pytest_asyncio.fixture
async def operator_user(make_user):
    return await make_user("operator")


@pytest_asyncio.fixture
async def admin_user(make_user):
    return await make_user("admin")


def auth_headers(user) -> dict:
    """Bypass the login round-trip when a test only needs a valid bearer token."""
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def make_uav_asset():
    created_ids = []

    async def _make(status: str = "active") -> UAVAsset:
        async with AsyncSessionLocal() as db:
            asset = UAVAsset(id=uuid.uuid4(), tail_number=f"TEST-{uuid.uuid4().hex[:8]}", status=status)
            db.add(asset)
            await db.commit()
            await db.refresh(asset)
            created_ids.append(asset.id)
            return asset

    yield _make

    async with AsyncSessionLocal() as db:
        for asset_id in created_ids:
            # Tests may create missions/engines against these throwaway
            # assets directly via the API (bypassing make_mission/make_engine),
            # so clear those first or the asset delete FK-violates.
            await db.execute(delete(Mission).where(Mission.uav_asset_id == asset_id))
            await db.execute(delete(Engine).where(Engine.uav_asset_id == asset_id))
            existing = await db.get(UAVAsset, asset_id)
            if existing:
                await db.delete(existing)
        await db.commit()


@pytest_asyncio.fixture
async def make_engine(make_uav_asset):
    created_ids = []

    async def _make(uav_asset_id=None) -> Engine:
        if uav_asset_id is None:
            uav_asset_id = (await make_uav_asset()).id
        async with AsyncSessionLocal() as db:
            engine = Engine(
                id=uuid.uuid4(),
                serial_number=f"TEST-ENGINE-{uuid.uuid4().hex[:8]}",
                uav_asset_id=uav_asset_id,
                status="operational",
            )
            db.add(engine)
            await db.commit()
            await db.refresh(engine)
            created_ids.append(engine.id)
            return engine

    yield _make

    async with AsyncSessionLocal() as db:
        for engine_id in created_ids:
            # Tests routinely create alerts/maintenance-logs/predictions
            # against these throwaway engines without their own cleanup;
            # deleting the engine first would FK-violate against them.
            for dependent in (
                Alert, MaintenanceLog, TelemetryReading,
                RulPrediction, FaultPrediction, AuxPrediction, BearingHealthReading,
                HealthScore, SimulationRun,
            ):
                await db.execute(delete(dependent).where(dependent.engine_id == engine_id))
            existing = await db.get(Engine, engine_id)
            if existing:
                await db.delete(existing)
        await db.commit()


@pytest_asyncio.fixture
async def make_mission(make_uav_asset):
    from datetime import datetime, timedelta, timezone

    created_ids = []

    async def _make(uav_asset_id=None, status: str = "scheduled") -> Mission:
        if uav_asset_id is None:
            uav_asset_id = (await make_uav_asset()).id
        async with AsyncSessionLocal() as db:
            mission = Mission(
                id=uuid.uuid4(),
                uav_asset_id=uav_asset_id,
                mission_type="endurance",
                start_time=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
                status=status,
            )
            db.add(mission)
            await db.commit()
            await db.refresh(mission)
            created_ids.append(mission.id)
            return mission

    yield _make

    async with AsyncSessionLocal() as db:
        for mission_id in created_ids:
            existing = await db.get(Mission, mission_id)
            if existing:
                await db.delete(existing)
        await db.commit()
