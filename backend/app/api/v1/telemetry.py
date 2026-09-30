import hmac
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from uuid import UUID

from app.core.config import settings
from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.engine import Engine as EngineModel
from app.models.telemetry_reading import TelemetryReading as TelemetryReadingModel
from app.schemas.telemetry import TelemetryReading as TelemetryReadingSchema
from app.services.validation import validate_payload

router = APIRouter()

MAX_RANGE_DAYS = 30
MAX_LIMIT = 5000
DEFAULT_LIMIT = 500


async def verify_edge_api_key(x_edge_api_key: str = Header(...)):
    """Auth for edge devices posting telemetry directly over REST (vs. MQTT)."""
    # Plain `!=` short-circuits on the first differing byte, leaking a
    # timing signal an attacker could use to brute-force the key one byte
    # at a time — compare_digest runs in time independent of where (or
    # whether) the strings first differ.
    if not hmac.compare_digest(x_edge_api_key, settings.EDGE_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid edge API key")


@router.post("/telemetry/ingest", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_edge_api_key)])
async def ingest_telemetry(payload: dict, db: AsyncSession = Depends(get_db)):
    """
    REST ingestion path for edge devices that can't use MQTT. Shares the
    same validation as the MQTT path (`app.services.validation`) so the
    two ingestion routes can never silently drift on what's plausible.
    """
    result = validate_payload(payload)
    if result.rejected:
        raise HTTPException(status_code=400, detail=result.reason)

    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == payload["engine_id"]))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Unknown engine_id")

    ts_raw = payload["ts"]
    if isinstance(ts_raw, str):
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    else:
        ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
    ts = ts.replace(tzinfo=None)

    reading = TelemetryReadingModel(
        ts=ts,
        engine_id=payload["engine_id"],
        mission_id=payload.get("mission_id"),
        rpm=payload["rpm"],
        cht=payload["cht"],
        egt=payload["egt"],
        oil_pressure=payload["oil_pressure"],
        oil_temp=payload["oil_temp"],
        fuel_flow=payload["fuel_flow"],
        vibration_x=payload.get("vibration_x"),
        vibration_y=payload.get("vibration_y"),
        vibration_z=payload.get("vibration_z"),
        throttle=payload.get("throttle"),
        altitude_m=payload.get("altitude_m"),
        quality_status=result.status.value,
    )
    db.add(reading)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        if "telemetry_readings_pkey" in str(e.orig):
            # (engine_id, ts) is the primary key — an edge device
            # retrying a request it never got a response for (a dropped
            # connection, a timeout) will resubmit the exact same
            # reading. That's a normal, expected retry pattern for
            # unreliable links, not a client error deserving a bare,
            # undifferentiated 500; treat the duplicate as
            # already-delivered rather than a failure.
            return {"status": "duplicate", "id": f"{reading.engine_id}:{reading.ts.isoformat()}"}
        raise HTTPException(status_code=400, detail="Invalid reference (e.g. unknown mission_id)")

    return {"status": "accepted", "id": f"{reading.engine_id}:{reading.ts.isoformat()}"}


@router.get("/engines/{engine_id}/telemetry", response_model=List[TelemetryReadingSchema])
async def get_telemetry_range(
    engine_id: UUID,
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Ranged telemetry query. Range is capped at 30 days to protect the hypertable."""
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    if from_ is not None and to is not None:
        if from_ >= to:
            raise HTTPException(status_code=400, detail="`from` must be before `to`")
        if (to - from_).days > MAX_RANGE_DAYS:
            raise HTTPException(status_code=400, detail=f"Range cannot exceed {MAX_RANGE_DAYS} days")

    query = select(TelemetryReadingModel).where(TelemetryReadingModel.engine_id == engine_id)
    if from_ is not None:
        query = query.where(TelemetryReadingModel.ts >= from_)
    if to is not None:
        query = query.where(TelemetryReadingModel.ts <= to)
    query = query.order_by(TelemetryReadingModel.ts.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()
