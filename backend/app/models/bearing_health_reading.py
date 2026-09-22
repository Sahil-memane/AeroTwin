from sqlalchemy import Column, ForeignKey, DateTime, String, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class BearingHealthReading(Base):
    __tablename__ = 'bearing_health_readings'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    fault_location = Column(String, nullable=False)
    severity_score = Column(Float, nullable=False)
