from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class FaultPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    fault_class: str
    confidence: float
    
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
    fault_location: str
    severity_score: float
    
    class Config:
        from_attributes = True

class AuxPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    aux_score: float
    
    class Config:
        from_attributes = True
