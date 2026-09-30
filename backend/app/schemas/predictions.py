from pydantic import BaseModel, computed_field
from uuid import UUID
from datetime import datetime
from typing import Optional

from app.services.fault_reliability import is_reliable

class FaultPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    class_id: int
    fault_class: str
    confidence: float
    probabilities: list[float]
    # Accuracy-First Phase 3 — temporal-consistency state machine
    # classification (see app/services/fault_state.py). None on rows
    # written before this column existed.
    state: Optional[str] = None
    # Share of model input channels driven by measured data; None on legacy rows.
    input_coverage: Optional[float] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reliable(self) -> bool:
        """False => advisory only: excluded from Health Fusion and alerts."""
        return is_reliable(self.input_coverage)

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
