from sqlalchemy import Column, ForeignKey, DateTime, Float, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class AuxPrediction(Base):
    __tablename__ = 'aux_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    failure_status = Column(String, nullable=False)
    risk_level = Column(String, nullable=False)
    failure_probability_pct = Column(Float, nullable=False)
    detected_failure_types = Column(JSON, nullable=False)
    primary_failure_cause = Column(String, nullable=True)
    recommended_action = Column(String, nullable=True)
