from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.engine import Engine as EngineModel
from app.models.bearing_health_reading import BearingHealthReading as BearingHealthReadingModel
from app.schemas.predictions import BearingHealthReading as BearingHealthReadingSchema
from uuid import UUID

router = APIRouter()


@router.get("/{engine_id}/bearing-health", response_model=BearingHealthReadingSchema)
async def get_latest_bearing_health(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Get the most recent bearing-health reading for an engine.

    Serves the model's real fields (class_id, class_label, fault_location,
    severity_inches, confidence) rather than the Implementation Document's
    Section 12.4 `severity_score`, which does not exist on this model —
    see the plan's Phase 4.0 sign-off note.
    """
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    result = await db.execute(
        select(BearingHealthReadingModel)
        .where(BearingHealthReadingModel.engine_id == engine_id)
        .order_by(BearingHealthReadingModel.ts.desc())
        .limit(1)
    )
    reading = result.scalars().first()
    if not reading:
        raise HTTPException(status_code=404, detail="No bearing-health reading available")
    return reading
