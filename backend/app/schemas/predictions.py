from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class FaultPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    class_id: int
    fault_class: str
    confidence: float
    probabilities: list[float]
    
    class Config:
        from_attributes = True

class RulPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    rul_cycles: float
    degradation_index: float
    
    class Config:
        from_attributes = True

class BearingHealthReading(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    class_id: int
    class_label: str
    fault_location: str
    severity_inches: Optional[float]   # null for Normal class
    confidence: float

    class Config:
        from_attributes = True

class AuxPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    failure_status: str
    risk_level: str
    failure_probability_pct: float
    detected_failure_types: list[dict]
    primary_failure_cause: Optional[str]
    recommended_action: Optional[str]
    
    class Config:
        from_attributes = True
