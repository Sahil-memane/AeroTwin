from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID
from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.engine import Engine
from app.schemas.engine import Engine as EngineSchema, EngineCreate

router = APIRouter()

@router.get("", response_model=List[EngineSchema])
async def read_engines(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    result = await db.execute(select(Engine))
    return result.scalars().all()

@router.post("", response_model=EngineSchema)
async def create_engine(
    engine_in: EngineCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_role(["admin", "program_manager"]))
):
    engine = Engine(**engine_in.model_dump())
    db.add(engine)
    await db.commit()
    await db.refresh(engine)
    return engine

@router.get("/{engine_id}/health-score")
async def get_health_score(
    engine_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    # Dummy implementation for Phase 1
    return {
        "combined_score": 100,
        "contributing_factors": [],
        "last_updated": "2026-09-22T00:00:00Z"
    }
