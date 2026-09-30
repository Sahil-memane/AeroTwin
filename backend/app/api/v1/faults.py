from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.engine import Engine as EngineModel
from app.models.fault_prediction import FaultPrediction as FaultPredictionModel
from app.schemas.predictions import FaultPrediction as FaultPredictionSchema
from uuid import UUID

router = APIRouter()


@router.get("/{engine_id}/faults/latest", response_model=FaultPredictionSchema)
async def get_latest_fault(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get the most recent fault prediction for an engine."""
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    result = await db.execute(
        select(FaultPredictionModel)
        .where(FaultPredictionModel.engine_id == engine_id)
        .order_by(FaultPredictionModel.ts.desc())
        .limit(1)
    )
    prediction = result.scalars().first()
    if not prediction:
        raise HTTPException(status_code=404, detail="No fault prediction available")
    return prediction
