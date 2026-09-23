from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime

class TelemetryIngestBase(BaseModel):
    engine_id: UUID
    mission_id: Optional[UUID] = None
    ts: datetime
    rpm: float
    cht: float
    egt: float
    oil_pressure: float
    oil_temp: float
    fuel_flow: float
    vibration_x: Optional[float] = None
    vibration_y: Optional[float] = None
    vibration_z: Optional[float] = None

class TelemetryReading(TelemetryIngestBase):
    class Config:
        from_attributes = True

class RulPrediction(BaseModel):
    engine_id: UUID
    ts: datetime
    rul_hours: float
    degradation_index: float

    class Config:
        from_attributes = True
