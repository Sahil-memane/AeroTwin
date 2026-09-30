from sqlalchemy import Column, ForeignKey, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class RulPrediction(Base):
    __tablename__ = 'rul_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)

    rul_cycles = Column(Float, nullable=False)
    degradation_index = Column(Float, nullable=False)

    # Accuracy-First Phase 2 — real split-conformal interval (see the
    # migration docstring for the calibration source), and what the
    # service observed at prediction time. NULL on rows written before
    # this column existed.
    rul_lower = Column(Float, nullable=True)
    rul_upper = Column(Float, nullable=True)
    status = Column(String, nullable=True)
