"""
Alert Engine — turns a Health Fusion result into a persisted, broadcast
Alert when warranted, per the Implementation Document's Phase 4
alerting logic:

  - combined_score < 50 (or forced-zero handled below) -> WARNING
  - combined_score < 20, or forced to 0 by a >90%-confidence fault -> CRITICAL
  - a cooldown window suppresses duplicate rapid-fire alerts of the same
    or lower severity for an engine, but an escalation (e.g. warning ->
    critical) always fires immediately even inside the window.

Cooldown state is kept in-process (a single backend replica, matching
the hackathon deployment target — see the plan's Phase 9 hardening
note: a multi-replica deployment would need this in Redis, which is
already provisioned in docker-compose.yml, but isn't needed yet).
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import Alert
from app.services.health_fusion import HealthScoreResult
from app.ws.connection_manager import manager as ws_manager

logger = logging.getLogger(__name__)

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
_SEVERITY_RANK = {SEVERITY_WARNING: 1, SEVERITY_CRITICAL: 2}

# Per-engine last-fired state: engine_id (str) -> (severity, fired_at).
# Process-local by design (see module docstring).
_last_alert: Dict[str, Tuple[str, datetime]] = {}


def _severity_for(result: HealthScoreResult) -> Optional[str]:
    if result.forced_zero or result.combined_score < 20:
        return SEVERITY_CRITICAL
    if result.combined_score < 50:
        return SEVERITY_WARNING
    return None


def _should_fire(engine_id: str, severity: str, now: datetime) -> bool:
    prior = _last_alert.get(engine_id)
    if prior is None:
        return True
    prior_severity, prior_fired_at = prior
    if _SEVERITY_RANK[severity] > _SEVERITY_RANK[prior_severity]:
        return True  # escalation always fires, even inside the cooldown window
    cooldown = timedelta(minutes=settings.ALERT_COOLDOWN_MINUTES)
    return now - prior_fired_at >= cooldown


def _build_message(contributing_factors) -> str:
    if not contributing_factors:
        return "Engine health degraded with no specific contributing factor recorded."

    parts = []
    for factor in contributing_factors:
        source = factor.get("source", "?")
        if source == "fault":
            conf_pct = round(factor.get("confidence", 0) * 100)
            tag = "critical" if factor.get("forced_zero") else f"-{factor.get('penalty')}pts"
            parts.append(f"Fault: {factor.get('fault_class')} ({conf_pct}% conf, {tag})")
        elif source == "rul":
            parts.append(f"RUL: {factor.get('rul_cycles')} cycles remaining (-{factor.get('penalty')}pts)")
        elif source == "bearing":
            parts.append(
                f"Bearing: {factor.get('class_label')} at {factor.get('fault_location')} (-{factor.get('penalty')}pts)"
            )
        elif source == "aux":
            parts.append(
                f"Aux: {factor.get('sub_failure') or 'unspecified'} risk "
                f"{factor.get('failure_probability_pct')}% (-{factor.get('penalty')}pts)"
            )
        else:
            parts.append(source)
    return " · ".join(parts)


def describe_alert(result: HealthScoreResult) -> Optional[Dict[str, str]]:
    """
    Pure (no DB, no broadcast, no cooldown) view of the alert a fusion
    result WOULD raise, using the exact production severity thresholds and
    message builder. Used by the What-If simulation, which must apply the
    same alert rules as production without ever creating or broadcasting a
    real alert. `evaluate_and_alert` below is unchanged.
    """
    severity = _severity_for(result)
    if severity is None:
        return None
    return {"source": "fusion", "severity": severity, "message": _build_message(result.contributing_factors)}


async def evaluate_and_alert(
    session: AsyncSession, engine_id, ts: datetime, result: HealthScoreResult
) -> Optional[Alert]:
    """
    Evaluate a fusion result and, if it crosses a severity threshold and
    isn't suppressed by the cooldown, persist and broadcast an Alert.
    Returns the created Alert, or None if nothing fired.
    """
    severity = _severity_for(result)
    if severity is None:
        return None

    engine_id_str = str(engine_id)
    if not _should_fire(engine_id_str, severity, ts):
        return None

    # Claim the cooldown slot synchronously, before any `await` — multiple
    # near-simultaneous MQTT messages for the same engine can each spawn
    # a concurrent _handle_message coroutine, and without this, two of
    # them can both pass the _should_fire check above (a check-then-act
    # race) before either had a chance to update _last_alert, since the
    # DB commit below yields control back to the event loop.
    _last_alert[engine_id_str] = (severity, ts)

    alert = Alert(
        engine_id=engine_id,
        source="fusion",
        severity=severity,
        message=_build_message(result.contributing_factors),
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)

    await ws_manager.broadcast_to_engine(engine_id_str, {
        "type": "alert",
        "payload": {
            "id": str(alert.id),
            "engine_id": engine_id_str,
            "source": alert.source,
            "severity": alert.severity,
            "message": alert.message,
            "created_at": ts.isoformat(),
        },
    })
    return alert
