from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.engine import Engine as EngineModel
from app.models.maintenance_log import MaintenanceLog as MaintenanceLogModel
from app.schemas.maintenance_log import MaintenanceLog as MaintenanceLogSchema, MaintenanceLogCreate

router = APIRouter()


@router.get("/{engine_id}/maintenance-logs", response_model=List[MaintenanceLogSchema])
async def list_maintenance_logs(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List maintenance actions logged against an engine, most recent first."""
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    result = await db.execute(
        select(MaintenanceLogModel)
        .where(MaintenanceLogModel.engine_id == engine_id)
        .order_by(MaintenanceLogModel.logged_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/{engine_id}/maintenance-logs",
    response_model=MaintenanceLogSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_log(
    engine_id: UUID,
    log_in: MaintenanceLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["maintenance_engineer", "program_manager", "admin"])),
):
    """Log a maintenance action taken on an engine."""
    engine_result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    if not engine_result.scalars().first():
        raise HTTPException(status_code=404, detail="Engine not found")

    log = MaintenanceLogModel(
        engine_id=engine_id,
        user_id=current_user.id,
        action_taken=log_in.action_taken,
        notes=log_in.notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
