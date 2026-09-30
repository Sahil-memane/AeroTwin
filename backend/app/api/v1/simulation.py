import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db, AsyncSessionLocal
from app.core.security import get_current_active_user, require_role
from app.models.engine import Engine as EngineModel
from app.models.mission import Mission as MissionModel
from app.models.telemetry_reading import TelemetryReading as TelemetryReadingModel
from app.models.simulation_run import SimulationRun as SimulationRunModel
from app.models.health_score import HealthScore as HealthScoreModel
from app.models.model_registry import ModelRegistry
from app.services import what_if_scenario

logger = logging.getLogger(__name__)
router = APIRouter()

# simulation/ lives at the repo root, a sibling of backend/ — add it to
# sys.path once so it's importable, same pattern as the copilot router
# uses for AeroTwin_Rag.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

MAX_REPLAY_READINGS = 300

# Keep strong references to in-flight background tasks — asyncio does not
# guarantee a task survives if nothing else holds a reference to it.
_background_tasks: set[asyncio.Task] = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


class SimulationRunCreate(BaseModel):
    engine_id: UUID
    mode: Literal["replay", "what_if"]
    mission_id: Optional[UUID] = None
    environmental_profile: Optional[dict] = None


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def create_simulation_run(
    body: SimulationRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["maintenance_engineer", "program_manager", "admin"])),
):
    """
    Kick off a replay (historical mission, re-run through the ML pipeline
    at accelerated speed) or a what-if (synthetic scenario) simulation.
    Runs in the background; poll `GET /simulation/{id}` for the result.
    """
    engine = (await db.execute(select(EngineModel).where(EngineModel.id == body.engine_id))).scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")

    if body.mode == "replay":
        if not body.mission_id or body.environmental_profile is not None:
            raise HTTPException(
                status_code=400, detail="replay mode requires exactly `mission_id` (no environmental_profile)"
            )
        mission = (await db.execute(select(MissionModel).where(MissionModel.id == body.mission_id))).scalars().first()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
    else:
        if not body.environmental_profile or body.mission_id is not None:
            raise HTTPException(
                status_code=400, detail="what_if mode requires exactly `environmental_profile` (no mission_id)"
            )

    run = SimulationRunModel(
        engine_id=body.engine_id,
        mode=body.mode,
        mission_id=body.mission_id,
        environmental_profile=body.environmental_profile,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    _spawn(_execute_run(run.id))

    return {"simulation_id": str(run.id), "status": "queued"}


class WhatIfRequest(BaseModel):
    engine_id: UUID
    # Window end. Omitted -> the engine's newest reading. Pinning it makes a
    # scenario reproducible against the baseline the operator was looking at.
    baseline_timestamp: Optional[datetime] = None
    # Parameter values are validated by what_if_scenario.validate_parameters
    # (typed loosely here so NaN/null/strings reach the validator and get a
    # clear INVALID_INPUT instead of a generic 422). Omitted keys = unchanged.
    parameters: dict[str, Any]


@router.get("/what-if/config")
async def get_what_if_config(current_user=Depends(get_current_active_user)):
    """Slider metadata (min/max/step/unit) and window settings for the What-If UI."""
    return {
        "parameters": what_if_scenario.parameter_config(),
        "perturbation_window": what_if_scenario.PERTURBATION_WINDOW,
        "required_readings": {
            "fault": what_if_scenario.fault_service.window_len,
            "rul": what_if_scenario.rul_service.window_len,
        },
        "feature_mapping": what_if_scenario.FEATURE_MAPPING,
    }


@router.post("/what-if")
async def run_what_if_scenario(
    body: WhatIfRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["maintenance_engineer", "program_manager", "admin"])),
):
    """
    Parameter-perturbation What-If: runs the engine's recent REAL telemetry
    window, with the requested parameter change applied in memory to the
    last K readings, through the existing RUL/Fault/Bearing/Aux models and
    Health Fusion, and compares against the unmodified window.

    Strictly read-only: writes no telemetry, predictions, health scores or
    alerts, broadcasts nothing, and does not touch live model state.
    Synchronous (returns the finished result; `simulation_status` says how
    it ended).
    """
    clean, errors = what_if_scenario.validate_parameters(body.parameters)
    if errors:
        raise HTTPException(status_code=400, detail={"simulation_status": "INVALID_INPUT", "errors": errors})

    engine = (await db.execute(select(EngineModel).where(EngineModel.id == body.engine_id))).scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")

    query = select(TelemetryReadingModel).where(TelemetryReadingModel.engine_id == body.engine_id)
    if body.baseline_timestamp is not None:
        ts_cut = body.baseline_timestamp
        if ts_cut.tzinfo is not None:
            ts_cut = ts_cut.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.where(TelemetryReadingModel.ts <= ts_cut)
    query = query.order_by(TelemetryReadingModel.ts.desc()).limit(what_if_scenario.required_window_size())
    fetched = (await db.execute(query)).scalars().all()
    rows = [
        {
            "ts": r.ts, "rpm": r.rpm, "cht": r.cht, "egt": r.egt, "oil_pressure": r.oil_pressure,
            "oil_temp": r.oil_temp, "fuel_flow": r.fuel_flow,
            "vibration_x": r.vibration_x, "vibration_y": r.vibration_y, "vibration_z": r.vibration_z,
            "throttle": r.throttle, "altitude_m": r.altitude_m,
        }
        for r in reversed(fetched)
    ]

    result = await asyncio.to_thread(what_if_scenario.run_scenario, str(body.engine_id), rows, clean)

    registry = (await db.execute(select(ModelRegistry).where(ModelRegistry.is_active.is_(True)))).scalars().all()
    versions = {r.model_name: r.version for r in registry}
    result["model_versions"] = {
        name: versions.get(name, "unregistered") for name in ("rul_model", "fault_model", "bearing_model", "aux_model")
    }
    # Reference only: the latest PERSISTED live score, clearly separate from
    # the recomputed baseline (which replays the window through the models).
    live = (await db.execute(
        select(HealthScoreModel).where(HealthScoreModel.engine_id == body.engine_id)
        .order_by(HealthScoreModel.ts.desc()).limit(1)
    )).scalars().first()
    result["live_reference"] = (
        {"combined_score": live.combined_score, "ts": live.ts.isoformat()} if live else None
    )
    return result


@router.get("/{simulation_id}")
async def get_simulation_run(
    simulation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    run = (await db.execute(select(SimulationRunModel).where(SimulationRunModel.id == simulation_id))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return {
        "simulation_id": str(run.id),
        "status": run.status,
        "mode": run.mode,
        "error": run.error,
        "results": run.results,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


async def _execute_run(run_id: UUID):
    async with AsyncSessionLocal() as session:
        run = (await session.execute(select(SimulationRunModel).where(SimulationRunModel.id == run_id))).scalars().first()
        if not run:
            return
        run.status = "running"
        await session.commit()

        try:
            # Imported inside the try block deliberately: an import-time
            # failure here (e.g. a path/module bug) must still mark the
            # run "failed" with a recorded error, not strand it at
            # "queued"/"running" forever with no visible cause.
            from simulation.replay_engine import run_sequence
            from simulation.scenario_generator import generate_what_if_telemetry
            from simulation.mission_profiles.presets import resolve_profile

            if run.mode == "replay":
                rows_result = await session.execute(
                    select(TelemetryReadingModel)
                    .where(
                        TelemetryReadingModel.engine_id == run.engine_id,
                        TelemetryReadingModel.mission_id == run.mission_id,
                    )
                    .order_by(TelemetryReadingModel.ts)
                )
                rows = rows_result.scalars().all()
                if not rows:
                    raise ValueError("No telemetry recorded for this engine/mission yet")
                if len(rows) > MAX_REPLAY_READINGS:
                    # Evenly downsample across the full mission duration
                    # rather than truncating to a tail — a replay should
                    # still span the whole mission, just at a coarser
                    # resolution, and keeps a demo-length scrubber (a few
                    # hundred points, not several thousand) fast to compute.
                    stride = len(rows) / MAX_REPLAY_READINGS
                    rows = [rows[int(i * stride)] for i in range(MAX_REPLAY_READINGS)]
                readings = [
                    {
                        "ts": r.ts.isoformat(),
                        "rpm": r.rpm,
                        "cht": r.cht,
                        "egt": r.egt,
                        "oil_pressure": r.oil_pressure,
                        "oil_temp": r.oil_temp,
                        "fuel_flow": r.fuel_flow,
                        "vibration_x": r.vibration_x,
                        "vibration_y": r.vibration_y,
                        "vibration_z": r.vibration_z,
                        "throttle": r.throttle,
                        "altitude_m": r.altitude_m,
                    }
                    for r in rows
                ]
            else:
                profile = resolve_profile(run.environmental_profile or {})
                readings = generate_what_if_telemetry(profile)

            # run_sequence is synchronous and CPU-bound (dozens–hundreds of
            # sequential sklearn/lightgbm/tensorflow inference calls) — run
            # it in a worker thread so it can't block the event loop (and
            # therefore every other request, including this run's own
            # GET /simulation/{id} poll and the live WebSocket broadcasts).
            results = await asyncio.to_thread(run_sequence, readings, str(run.id))
            run.results = results
            run.status = "completed"
        except Exception as e:
            logger.exception("Simulation run %s failed", run_id)
            run.status = "failed"
            run.error = str(e)
        finally:
            run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()
