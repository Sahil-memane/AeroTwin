from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from uuid import UUID

from app.db.session import get_db
from app.core.security import get_current_active_user, require_role
from app.models.alert import Alert as AlertModel
from app.schemas.alert import Alert as AlertSchema

router = APIRouter()


@router.get("", response_model=List[AlertSchema])
async def list_alerts(
    engine_id: Optional[UUID] = Query(None),
    severity: Optional[str] = Query(None),
    is_acknowledged: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """
    List alerts, filterable by engine, severity, and acknowledgement state.
    `is_acknowledged` omitted returns both; explicit true/false filters.
    """
    if severity is not None and severity not in ("warning", "critical"):
        raise HTTPException(status_code=400, detail="severity must be 'warning' or 'critical'")

    query = select(AlertModel)
    if is_acknowledged is not None:
        query = query.where(AlertModel.is_acknowledged == is_acknowledged)
    if engine_id is not None:
        query = query.where(AlertModel.engine_id == engine_id)
    if severity is not None:
        query = query.where(AlertModel.severity == severity)
    query = query.order_by(AlertModel.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/{alert_id}/acknowledge", response_model=AlertSchema)
async def acknowledge_alert(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(["maintenance_engineer", "program_manager", "admin"])),
):
    """Acknowledge an alert. Idempotent-safe: acknowledging twice is a 409."""
    result = await db.execute(select(AlertModel).where(AlertModel.id == alert_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.is_acknowledged:
        raise HTTPException(status_code=409, detail="Alert already acknowledged")

    alert.is_acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(alert)
    return alert
