from sqlalchemy import Column, ForeignKey, DateTime, String, Float, CheckConstraint, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class FaultPrediction(Base):
    __tablename__ = 'fault_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    class_id = Column(Integer, nullable=False)
    fault_class = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    probabilities = Column(JSON, nullable=False)

    __table_args__ = (
        CheckConstraint("fault_class IN ('No Failure', 'RC Failure', 'GPS Failure', 'Accelerometer Failure', 'Gyro Failure', 'Compass Failure', 'Barometer Failure')", name='valid_fault_class'),
    )
