"""
Simulator control API.

Provides on-demand start/stop of the live-telemetry simulator for a given
engine.  In production (Docker) this manages the `aerotwin-simulator` container
via the Docker socket mounted into the backend container.

Endpoints:
  POST  /api/v1/simulator/{engine_id}/start      — start simulator (idempotent)
  POST  /api/v1/simulator/{engine_id}/stop       — explicitly stop simulator
  POST  /api/v1/simulator/{engine_id}/heartbeat  — lightweight ping to keep watchdog satisfied
  POST  /api/v1/simulator/stop-all               — stop ALL running simulators (logout / window-close)
  GET   /api/v1/simulator/{engine_id}/status     — query current state (no side-effects)

Access control:  any authenticated active user can start/stop a simulator.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security import get_current_active_user
from app.db.session import get_db
from app.models.engine import Engine as EngineModel
from app.services.simulator_manager import simulator_manager

logger = logging.getLogger(__name__)
router = APIRouter()


async def _assert_engine(engine_id: UUID, db: AsyncSession) -> None:
    """Raise 404 if the engine does not exist."""
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")


@router.post("/{engine_id}/start")
async def start_simulator(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Start the simulator for the given engine.  Idempotent — calling again when
    already running just refreshes the heartbeat.  The simulator keeps running
    until the user explicitly clicks Stop or logs out/closes the browser.
    """
    await _assert_engine(engine_id, db)
    try:
        result = await simulator_manager.start(str(engine_id))
    except Exception as exc:
        logger.exception("Failed to start simulator for engine %s", engine_id)
        raise HTTPException(status_code=503, detail=f"Could not start simulator: {exc}") from exc
    return result


@router.post("/{engine_id}/stop")
async def stop_simulator(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Explicitly stop the simulator for the given engine.
    This is the ONLY way the simulator stops (besides the 24-hour safety-net watchdog).
    Navigating away from the Dashboard does NOT stop it.
    """
    await _assert_engine(engine_id, db)
    try:
        result = await simulator_manager.stop(str(engine_id))
    except Exception as exc:
        logger.exception("Failed to stop simulator for engine %s", engine_id)
        raise HTTPException(status_code=503, detail=f"Could not stop simulator: {exc}") from exc
    return result


@router.post("/{engine_id}/heartbeat")
async def simulator_heartbeat(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Lightweight heartbeat ping.  Refreshes the watchdog timestamp so the
    safety-net doesn't kill an active simulator.  Called every 60 s by the
    global SimulatorStore (persists across page navigation).
    """
    await _assert_engine(engine_id, db)
    simulator_manager.heartbeat(str(engine_id))
    return {"ok": True}


@router.post("/stop-all")
async def stop_all_simulators(
    current_user=Depends(get_current_active_user),
):
    """
    Stop ALL running simulators.  Called on logout and browser window/tab close
    via the global beforeunload handler so the container is always cleaned up.
    No engine_id required — stops everything running for this deployment.
    """
    stopped = []
    for engine_id, running in list(simulator_manager._running.items()):
        if running:
            try:
                await simulator_manager.stop(engine_id, force=True)
                stopped.append(engine_id)
            except Exception:
                logger.exception("stop-all: failed to stop engine %s", engine_id)
    return {"stopped": stopped}


@router.delete("/{engine_id}")
async def force_stop_simulator(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Force-stop the simulator for the given engine regardless of state."""
    await _assert_engine(engine_id, db)
    try:
        result = await simulator_manager.stop(str(engine_id), force=True)
    except Exception as exc:
        logger.exception("Force-stop failed for engine %s", engine_id)
        raise HTTPException(status_code=503, detail=f"Could not force-stop simulator: {exc}") from exc
    return result


@router.get("/{engine_id}/status")
async def get_simulator_status(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Query whether the simulator is currently running. No side effects."""
    await _assert_engine(engine_id, db)
    return simulator_manager.status(str(engine_id))
