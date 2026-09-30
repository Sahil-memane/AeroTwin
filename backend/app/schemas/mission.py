from pydantic import BaseModel
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime

class MissionBase(BaseModel):
    uav_asset_id: UUID
    mission_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    environmental_profile: Optional[Dict[str, Any]] = None
    status: str = 'scheduled'

class MissionCreate(MissionBase):
    pass

class MissionUpdate(BaseModel):
    status: Optional[str] = None
    end_time: Optional[datetime] = None

class Mission(MissionBase):
    id: UUID

    class Config:
        from_attributes = True


class MissionListItem(Mission):
    """A mission in the list view. The recorded-data fields are only filled
    when the caller asks for them (`GET /missions?include_stats=true`) — they
    need an aggregate over telemetry_readings, so the plain list stays cheap.
    `reading_count` is 0 (not None) for a mission with no stored telemetry."""
    reading_count: Optional[int] = None
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None


class TelemetrySummary(BaseModel):
    reading_count: int
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None
    rpm_avg: Optional[float] = None
    rpm_max: Optional[float] = None
    cht_avg: Optional[float] = None
    cht_max: Optional[float] = None
    egt_avg: Optional[float] = None
    egt_max: Optional[float] = None
    oil_pressure_min: Optional[float] = None
    fuel_flow_avg: Optional[float] = None


class MissionDetail(Mission):
    telemetry_summary: Optional[TelemetrySummary] = None
