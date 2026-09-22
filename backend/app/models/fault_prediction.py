from sqlalchemy import Column, ForeignKey, DateTime, String, Float, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class FaultPrediction(Base):
    __tablename__ = 'fault_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    fault_class = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint("fault_class IN ('No failure', 'RC', 'GPS', 'Aileron', 'Elevator', 'Rudder', 'Engine failure')", name='valid_fault_class'),
    )
