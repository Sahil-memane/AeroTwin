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
from app.models.health_score import HealthScore

router = APIRouter()


@router.get("/summary")
async def dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Return a high-level dashboard summary, including fused fleet health and recent alerts."""
    # Total counts
    engine_count = await db.execute(select(func.count(Engine.id)))
    uav_count = await db.execute(select(func.count(UAVAsset.id)))
    # "active" is the status value actually used everywhere a mission is
    # marked as currently underway (missions.py's conflict check, the
    # seeded demo mission) — "in_progress" was never set by any code
    # path, so this KPI silently read 0 even with a real active mission.
    active_missions = await db.execute(
        select(func.count(Mission.id)).where(Mission.status == "active")
    )
    open_alerts = await db.execute(
        select(func.count(Alert.id)).where(Alert.is_acknowledged == False)  # noqa: E712
    )

    # Latest health_scores row per engine (window function), for fleet-wide averaging.
    row_number_col = func.row_number().over(
        partition_by=HealthScore.engine_id, order_by=HealthScore.ts.desc()
    ).label("rn")
    latest_per_engine = select(HealthScore.combined_score, row_number_col).subquery()
    latest_scores_result = await db.execute(
        select(latest_per_engine.c.combined_score).where(latest_per_engine.c.rn == 1)
    )
    scores = [row[0] for row in latest_scores_result.all()]

    average_score = round(sum(scores) / len(scores), 2) if scores else None
    engines_critical = sum(1 for s in scores if s < 20)
    engines_warning = sum(1 for s in scores if 20 <= s < 50)
    engines_healthy = sum(1 for s in scores if s >= 50)

    recent_alerts_result = await db.execute(
        select(Alert).order_by(Alert.created_at.desc()).limit(5)
    )
    recent_alerts = [
        {
            "id": str(a.id),
            "engine_id": str(a.engine_id),
            "source": a.source,
            "severity": a.severity,
            "message": a.message,
            "is_acknowledged": a.is_acknowledged,
            "created_at": a.created_at,
        }
        for a in recent_alerts_result.scalars().all()
    ]

    return {
        "total_engines": engine_count.scalar() or 0,
        "total_uav_assets": uav_count.scalar() or 0,
        "active_missions": active_missions.scalar() or 0,
        "open_alerts": open_alerts.scalar() or 0,
        "fleet_health": {
            "average_score": average_score,
            "engines_critical": engines_critical,
            "engines_warning": engines_warning,
            "engines_healthy": engines_healthy,
        },
        "recent_alerts": recent_alerts,
    }
