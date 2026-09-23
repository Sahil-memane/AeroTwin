from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.engine import Engine as EngineModel
from app.schemas.engine import Engine as EngineSchema, EngineCreate, EngineUpdate

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
):
    """Get the health score for an engine. Stub for Phase 1."""
    # Verify engine exists
    result = await db.execute(select(EngineModel).where(EngineModel.id == engine_id))
    engine = result.scalars().first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")

    return {
        "engine_id": str(engine_id),
        "combined_score": 100.0,
        "contributing_factors": [],
        "status": "healthy",
        "last_updated": None,
    }
