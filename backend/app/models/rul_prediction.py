from sqlalchemy import Column, ForeignKey, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class RulPrediction(Base):
    __tablename__ = 'rul_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    rul_cycles = Column(Float, nullable=False)
    degradation_index = Column(Float, nullable=False)
