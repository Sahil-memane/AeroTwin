from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.mission import Mission as MissionModel
from app.schemas.mission import Mission as MissionSchema, MissionCreate, MissionUpdate

router = APIRouter()


@router.get("", response_model=List[MissionSchema])
async def list_missions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List all missions. Any authenticated user."""
    result = await db.execute(select(MissionModel).order_by(MissionModel.start_time.desc()))
    return result.scalars().all()


@router.get("/{mission_id}", response_model=MissionSchema)
async def get_mission(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get a single mission by ID."""
    result = await db.execute(select(MissionModel).where(MissionModel.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("", response_model=MissionSchema, status_code=status.HTTP_201_CREATED)
async def create_mission(
    mission_in: MissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "operator", "program_manager"])),
):
    """Create a new mission. Operator, Program Manager, or Admin."""
    mission = MissionModel(**mission_in.model_dump())
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.put("/{mission_id}", response_model=MissionSchema)
async def update_mission(
    mission_id: UUID,
    mission_in: MissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "operator", "program_manager"])),
):
    """Update a mission. Operator, Program Manager, or Admin."""
    result = await db.execute(select(MissionModel).where(MissionModel.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")

    update_data = mission_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(mission, field, value)

    await db.commit()
    await db.refresh(mission)
    return mission


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Delete a mission. Admin only."""
    result = await db.execute(select(MissionModel).where(MissionModel.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    await db.delete(mission)
    await db.commit()
