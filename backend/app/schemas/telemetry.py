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
    throttle: Optional[float] = None
    altitude_m: Optional[float] = None

class TelemetryReading(TelemetryIngestBase):
    quality_status: Optional[str] = None

    class Config:
        from_attributes = True

class RulPrediction(BaseModel):
    engine_id: UUID
    ts: datetime
    rul_cycles: float
    degradation_index: float
    # Accuracy-First Phase 2 — real split-conformal interval + what the
    # service observed at prediction time. Optional/None on rows written
    # before these columns existed.
    rul_lower: Optional[float] = None
    rul_upper: Optional[float] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True
