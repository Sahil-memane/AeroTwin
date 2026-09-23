from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.db.session import get_db
from app.core.security import get_current_active_user
from app.models.engine import Engine
from app.models.uav_asset import UAVAsset
from app.models.alert import Alert
from app.models.mission import Mission

router = APIRouter()


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    Return a high-level dashboard summary.
    Phase 1: returns correctly-shaped payload with real counts.
    Prediction-related fields will be populated in Phase 4.
    """
    # Total counts
    engine_count = await db.execute(select(func.count(Engine.id)))
    uav_count = await db.execute(select(func.count(UAVAsset.id)))
    active_missions = await db.execute(
        select(func.count(Mission.id)).where(Mission.status == "in_progress")
    )
    open_alerts = await db.execute(
        select(func.count(Alert.id)).where(Alert.is_acknowledged == False)  # noqa: E712
    )

    return {
        "total_engines": engine_count.scalar() or 0,
        "total_uav_assets": uav_count.scalar() or 0,
        "active_missions": active_missions.scalar() or 0,
        "open_alerts": open_alerts.scalar() or 0,
        "fleet_health": {
            "average_score": None,  # Populated in Phase 4
            "engines_critical": 0,
            "engines_warning": 0,
            "engines_healthy": 0,
        },
        "recent_alerts": [],  # Populated in Phase 4
    }
