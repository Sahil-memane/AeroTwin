from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.uav_asset import UAVAsset as UAVAssetModel
from app.schemas.uav_asset import UAVAsset as UAVAssetSchema, UAVAssetCreate, UAVAssetUpdate

router = APIRouter()


@router.get("", response_model=List[UAVAssetSchema])
async def list_uav_assets(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List all UAV assets. Any authenticated user."""
    result = await db.execute(select(UAVAssetModel).order_by(UAVAssetModel.tail_number))
    return result.scalars().all()


@router.get("/{asset_id}", response_model=UAVAssetSchema)
async def get_uav_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get a single UAV asset by ID."""
    result = await db.execute(select(UAVAssetModel).where(UAVAssetModel.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="UAV asset not found")
    return asset


@router.post("", response_model=UAVAssetSchema, status_code=status.HTTP_201_CREATED)
async def create_uav_asset(
    asset_in: UAVAssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "program_manager"])),
):
    """Create a new UAV asset. Admin or Program Manager only."""
    # Check duplicate tail number
    existing = await db.execute(
        select(UAVAssetModel).where(UAVAssetModel.tail_number == asset_in.tail_number)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A UAV asset with this tail number already exists",
        )

    asset = UAVAssetModel(**asset_in.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.put("/{asset_id}", response_model=UAVAssetSchema)
async def update_uav_asset(
    asset_id: UUID,
    asset_in: UAVAssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "program_manager"])),
):
    """Update a UAV asset. Admin or Program Manager only."""
    result = await db.execute(select(UAVAssetModel).where(UAVAssetModel.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="UAV asset not found")

    update_data = asset_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_uav_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Delete a UAV asset. Admin only."""
    result = await db.execute(select(UAVAssetModel).where(UAVAssetModel.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="UAV asset not found")
    await db.delete(asset)
    await db.commit()
