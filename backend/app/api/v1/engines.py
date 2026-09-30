from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from uuid import UUID
from jose import jwt, JWTError

from app.db.session import get_db
from app.core.config import settings
from app.core.security import get_current_active_user, require_role
from app.models.engine import Engine as EngineModel
from app.models.telemetry_reading import TelemetryReading as TelemetryReadingModel
from app.models.rul_prediction import RulPrediction as RulPredictionModel
from app.models.health_score import HealthScore as HealthScoreModel
from app.models.physics_deviation_reading import PhysicsDeviationReading as PhysicsDeviationReadingModel
from app.schemas.engine import Engine as EngineSchema, EngineCreate, EngineUpdate
from app.schemas.telemetry import TelemetryReading as TelemetryReadingSchema, RulPrediction as RulPredictionSchema
from app.ws.connection_manager import manager as ws_manager
from app.services.rul_service import rul_service

router = APIRouter()


@router.get("", response_model=List[EngineSchema])
async def list_engines(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List all engines. Any authenticated user."""
    result = await db.execute(select(EngineModel).order_by(EngineModel.serial_number))
    return result.scalars().all()


@router.get("/{engine_id}", response_model=EngineSchema)
async def get_engine(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get a single engine by ID."""
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    engine = result.scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")
    return engine


@router.post("", response_model=EngineSchema, status_code=status.HTTP_201_CREATED)
async def create_engine(
    engine_in: EngineCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "program_manager"])),
):
    """Create a new engine. Admin or Program Manager only."""
    # Check duplicate serial number
    existing = await db.execute(
        select(EngineModel).where(EngineModel.serial_number == engine_in.serial_number)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An engine with this serial number already exists",
        )

    engine = EngineModel(**engine_in.model_dump())
    db.add(engine)
    await db.commit()
    await db.refresh(engine)
    return engine


@router.put("/{engine_id}", response_model=EngineSchema)
async def update_engine(
    engine_id: UUID,
    engine_in: EngineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "program_manager", "maintenance_engineer"])),
):
    """Update an engine. Admin, Program Manager, or Maintenance Engineer."""
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    engine = result.scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")

    update_data = engine_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(engine, field, value)

    await db.commit()
    await db.refresh(engine)
    return engine


@router.delete("/{engine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engine(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Delete an engine. Admin only."""
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    engine = result.scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")
    await db.delete(engine)
    await db.commit()


@router.get("/{engine_id}/health-score")
async def get_health_score(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    history_limit: int = 50,
):
    """
    Get the current fused health score for an engine, plus a recent
    historical trend (computed by `health_fusion.py` on every telemetry
    message and persisted to `health_scores` — see Phase 4).
    """
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    engine = result.scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")

    trend_result = await db.execute(
        select(HealthScoreModel)
        .where(HealthScoreModel.engine_id == engine_id)
        .order_by(HealthScoreModel.ts.desc())
        .limit(history_limit)
    )
    history = trend_result.scalars().all()
    latest = history[0] if history else None

    if latest is None:
        # Accuracy-First Phase 2: a never-evaluated engine has no health
        # score — it is NOT "perfectly healthy." Fabricating
        # combined_score=100.0 here (the previous behavior) was exactly
        # the anti-pattern the source document calls out: a brand-new
        # engine that had never been assessed showed as fully healthy on
        # the dashboard, indistinguishable from a real 100.
        combined_score, contributing_factors, last_updated, primary_concern = None, [], None, None
        status_label = "insufficient_data"
    else:
        combined_score, contributing_factors, last_updated = (
            latest.combined_score, latest.contributing_factors, latest.ts,
        )
        # Accuracy-First Phase 5 — NULL on rows written before this
        # column existed, or when there was genuinely nothing to report.
        primary_concern = getattr(latest, "primary_concern", None)
        if combined_score < 20:
            status_label = "critical"
        elif combined_score < 50:
            status_label = "warning"
        else:
            status_label = "healthy"

    # A score is only as current as the data behind it: flag it (rather than
    # hide it) when the newest persisted score is old, e.g. the engine has
    # stopped streaming.
    age_seconds = (
        (datetime.now(timezone.utc).replace(tzinfo=None) - last_updated).total_seconds()
        if last_updated is not None else None
    )
    stale = age_seconds is not None and age_seconds > settings.HEALTH_SCORE_STALE_AFTER_SECONDS

    return {
        "engine_id": str(engine_id),
        "combined_score": combined_score,
        "contributing_factors": contributing_factors,
        "primary_concern": primary_concern,
        "status": status_label,
        "last_updated": last_updated,
        "age_seconds": age_seconds,
        "stale": stale,
        "history": [
            {"ts": row.ts, "combined_score": row.combined_score} for row in reversed(history)
        ],
    }


@router.get("/{engine_id}/telemetry/latest", response_model=TelemetryReadingSchema)
async def get_latest_telemetry(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get the most recent telemetry reading for an engine."""
    # Verify engine exists
    engine_result = await db.execute(
        select(EngineModel).where(EngineModel.id == engine_id)
    )
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    result = await db.execute(
        select(TelemetryReadingModel)
        .where(TelemetryReadingModel.engine_id == engine_id)
        .order_by(TelemetryReadingModel.ts.desc())
        .limit(1)
    )
    reading = result.scalars().first()
    if not reading:
        raise HTTPException(status_code=404, detail="No telemetry data available")
    return reading


@router.get("/{engine_id}/rul", response_model=List[RulPredictionSchema])
async def get_rul_predictions(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
    limit: int = 100,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
):
    """
    Get the most recent RUL predictions for an engine, optionally ranged
    by `from`/`to`. NOTE: this endpoint (not a separate `api/v1/rul.py`
    router) is the one and only implementation of `GET .../rul` — a
    second router mounted under the same `engines` prefix at the same
    path would create an ambiguous route, so `rul.py` is intentionally
    left empty. See the Phase 4.0 plan notes.
    """
    # Verify engine exists
    engine_result = await db.execute(
        select(EngineModel).where(EngineModel.id == engine_id)
    )
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    query = select(RulPredictionModel).where(RulPredictionModel.engine_id == engine_id)
    if from_ is not None:
        query = query.where(RulPredictionModel.ts >= from_)
    if to is not None:
        query = query.where(RulPredictionModel.ts <= to)
    query = query.order_by(RulPredictionModel.ts.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{engine_id}/rul/status")
async def get_rul_status(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Accuracy-First Phase 2. Distinguishes "this engine has never had
    enough telemetry to produce a RUL prediction yet" from "no
    prediction has ever been persisted" (previously indistinguishable —
    both showed as an empty `GET /rul` list). Reads `rul_service`'s
    in-memory window depth directly — no DB query, O(1), always
    up to date with the live ingestion process this API server runs in.
    """
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    window_len = rul_service.window_len
    samples_collected = rul_service.get_window_depth(str(engine_id))

    latest = (
        await db.execute(
            select(RulPredictionModel)
            .where(RulPredictionModel.engine_id == engine_id)
            .order_by(RulPredictionModel.ts.desc())
            .limit(1)
        )
    ).scalars().first()

    if latest is not None:
        rul_status = latest.status or "VALID"  # NULL = written before Phase 2, treat as valid
    elif samples_collected > 0:
        rul_status = "INSUFFICIENT_DATA"
    else:
        rul_status = "INITIALIZING"

    return {
        "engine_id": str(engine_id),
        "status": rul_status,
        "samples_collected": samples_collected,
        "samples_required": window_len,
        "last_prediction_ts": latest.ts if latest else None,
    }


@router.get("/{engine_id}/physics-consistency")
async def get_physics_consistency(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Accuracy-First Phase 4. The latest expected-vs-measured comparison
    for each of the 5 channels the Otto-cycle physics model covers
    (CHT, EGT, oil pressure, oil temp, fuel flow) — computed by every
    live ingestion cycle (`physics_ingestion.py`) and persisted to
    `physics_deviation_readings`, one row per (engine, ts, parameter).
    Uses Postgres `DISTINCT ON` since each channel can in principle be
    updated at a slightly different cadence — this always returns each
    channel's own most recent row, not just the 5 rows from one ts.
    """
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    result = await db.execute(
        select(PhysicsDeviationReadingModel)
        .where(PhysicsDeviationReadingModel.engine_id == engine_id)
        .distinct(PhysicsDeviationReadingModel.parameter)
        .order_by(PhysicsDeviationReadingModel.parameter, PhysicsDeviationReadingModel.ts.desc())
    )
    rows = result.scalars().all()

    return {
        "engine_id": str(engine_id),
        "parameters": [
            {
                "parameter": row.parameter,
                "ts": row.ts,
                "expected": row.expected,
                "measured": row.measured,
                "residual": row.residual,
                "status": row.status,
                "method": row.method,
            }
            for row in sorted(rows, key=lambda r: r.ts, reverse=True)
        ],
    }


@router.websocket("/{engine_id}/live")
async def websocket_live_telemetry(
    websocket: WebSocket,
    engine_id: UUID,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for live telemetry streaming.
    JWT is validated from the `token` query parameter at handshake time.
    Pushes  { "type": "telemetry", "payload": {...} }  for each new reading.
    """
    # ── JWT validation at handshake ──
    if not token:
        await websocket.close(code=4001, reason="Missing token query parameter")
        return

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    engine_id_str = str(engine_id)
    await ws_manager.connect(websocket, engine_id_str)

    try:
        # Keep the connection alive — the ingestion service pushes data
        while True:
            # Wait for any client-side message (ping/pong keep-alive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, engine_id_str)
    except Exception:
        ws_manager.disconnect(websocket, engine_id_str)

