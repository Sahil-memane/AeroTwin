from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.mission import Mission as MissionModel
from app.models.uav_asset import UAVAsset as UAVAssetModel
from app.models.telemetry_reading import TelemetryReading as TelemetryReadingModel
from app.schemas.mission import (
    Mission as MissionSchema,
    MissionCreate,
    MissionUpdate,
    MissionDetail,
    MissionListItem,
    TelemetrySummary,
)

router = APIRouter()


async def _build_telemetry_summary(db: AsyncSession, mission_id: UUID) -> TelemetrySummary | None:
    """One aggregate query over this mission's own readings — never the
    raw rows themselves, which is exactly the "no depth" gap this was
    built to close without turning the mission detail view into a
    second telemetry-range endpoint."""
    row = (
        await db.execute(
            select(
                func.count(TelemetryReadingModel.ts),
                func.min(TelemetryReadingModel.ts),
                func.max(TelemetryReadingModel.ts),
                func.avg(TelemetryReadingModel.rpm),
                func.max(TelemetryReadingModel.rpm),
                func.avg(TelemetryReadingModel.cht),
                func.max(TelemetryReadingModel.cht),
                func.avg(TelemetryReadingModel.egt),
                func.max(TelemetryReadingModel.egt),
                func.min(TelemetryReadingModel.oil_pressure),
                func.avg(TelemetryReadingModel.fuel_flow),
            ).where(TelemetryReadingModel.mission_id == mission_id)
        )
    ).one()
    count = row[0] or 0
    if count == 0:
        return None
    return TelemetrySummary(
        reading_count=count,
        first_ts=row[1], last_ts=row[2],
        rpm_avg=row[3], rpm_max=row[4],
        cht_avg=row[5], cht_max=row[6],
        egt_avg=row[7], egt_max=row[8],
        oil_pressure_min=row[9],
        fuel_flow_avg=row[10],
    )


@router.get("", response_model=List[MissionListItem])
async def list_missions(
    include_stats: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """List all missions. Any authenticated user.

    With `include_stats=true` each mission also carries how much telemetry is
    stored for it (`reading_count`, `first_ts`, `last_ts`) — what a Replay
    picker needs to tell a mission with data from an empty one. One grouped
    query over just the listed missions, not one per row."""
    missions = (await db.execute(select(MissionModel).order_by(MissionModel.start_time.desc()))).scalars().all()
    items = [MissionListItem.model_validate(m) for m in missions]
    if include_stats and items:
        rows = (
            await db.execute(
                select(
                    TelemetryReadingModel.mission_id,
                    func.count(TelemetryReadingModel.ts),
                    func.min(TelemetryReadingModel.ts),
                    func.max(TelemetryReadingModel.ts),
                )
                .where(TelemetryReadingModel.mission_id.in_([m.id for m in items]))
                .group_by(TelemetryReadingModel.mission_id)
            )
        ).all()
        stats = {r[0]: r for r in rows}
        for item in items:
            r = stats.get(item.id)
            item.reading_count = r[1] if r else 0
            item.first_ts = r[2] if r else None
            item.last_ts = r[3] if r else None
    return items


@router.get("/{mission_id}", response_model=MissionDetail)
async def get_mission(
    mission_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get a single mission by ID, with a compact telemetry summary —
    never the raw readings themselves (see /engines/{id}/telemetry for
    that, already range/limit-capped)."""
    result = await db.execute(select(MissionModel).where(MissionModel.id == mission_id))
    mission = result.scalars().first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    summary = await _build_telemetry_summary(db, mission_id)
    return MissionDetail(**MissionSchema.model_validate(mission).model_dump(), telemetry_summary=summary)


@router.post("", response_model=MissionSchema, status_code=status.HTTP_201_CREATED)
async def create_mission(
    mission_in: MissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["admin", "operator", "program_manager"])),
):
    """Create a new mission. Operator, Program Manager, or Admin."""
    data = mission_in.model_dump()
    # `start_time`/`end_time` columns are TIMESTAMP WITHOUT TIME ZONE; a
    # timezone-aware value (the normal shape for an ISO8601 payload with
    # a UTC offset) crashes asyncpg with "can't subtract offset-naive and
    # offset-aware datetimes" unless stripped first, same as ingestion.py
    # already does for telemetry timestamps.
    for field in ("start_time", "end_time"):
        if data.get(field) is not None:
            data[field] = data[field].replace(tzinfo=None)

    if data["start_time"] < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=400, detail="start_time cannot be in the past")

    asset = (await db.execute(select(UAVAssetModel).where(UAVAssetModel.id == data["uav_asset_id"]))).scalars().first()
    if not asset:
        raise HTTPException(status_code=400, detail="uav_asset_id does not exist")
    if asset.status != "active":
        raise HTTPException(status_code=400, detail=f"UAV asset '{asset.tail_number}' is not active (status={asset.status})")

    conflicting = (
        await db.execute(
            select(MissionModel).where(
                MissionModel.uav_asset_id == data["uav_asset_id"],
                MissionModel.status == "active",
            )
        )
    ).scalars().first()
    if conflicting:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"UAV asset '{asset.tail_number}' already has an active mission",
        )

    mission = MissionModel(**data)
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
    if update_data.get("end_time") is not None:
        update_data["end_time"] = update_data["end_time"].replace(tzinfo=None)
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
