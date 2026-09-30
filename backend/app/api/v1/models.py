from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional

from app.db.session import get_db
from app.core.security import require_role
from app.models.model_registry import ModelRegistry as ModelRegistryModel
from app.schemas.model_registry import ModelRegistry as ModelRegistrySchema

router = APIRouter()

KNOWN_MODEL_NAMES = {"fault_lgb_2stage", "rul_xgb_base", "bearing_vibration_cnn", "aux_predictive_maintenance"}


@router.get("", response_model=List[ModelRegistrySchema])
async def list_models(
    model_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["maintenance_engineer", "program_manager", "admin"])),
):
    """
    List registered model versions, optionally filtered by model_name.

    Serves the ModelRegistry table's real columns (model_name, version,
    is_active, validation_score, registered_at) — the Implementation
    Document's Section 12.4 `framework`/`trained_at` fields don't exist on
    this table and aren't invented here; see the plan's Phase 4.0 sign-off.
    """
    if model_name is not None and model_name not in KNOWN_MODEL_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown model_name. Must be one of {sorted(KNOWN_MODEL_NAMES)}")

    query = select(ModelRegistryModel).order_by(ModelRegistryModel.model_name, ModelRegistryModel.registered_at.desc())
    if model_name is not None:
        query = query.where(ModelRegistryModel.model_name == model_name)

    result = await db.execute(query)
    return result.scalars().all()
