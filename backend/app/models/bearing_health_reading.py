from sqlalchemy import Column, ForeignKey, DateTime, String, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class BearingHealthReading(Base):
    __tablename__ = 'bearing_health_readings'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)

    # Full CNN output
    class_id         = Column(Integer, nullable=False)            # 0-9
    class_label      = Column(String, nullable=False)             # e.g. "Ball_007"
    fault_location   = Column(String, nullable=False)             # e.g. "Ball / Rolling Element"
    severity_inches  = Column(Float, nullable=True)               # 0.007/0.014/0.021 or NULL for Normal
    confidence       = Column(Float, nullable=False)              # 0.0 – 1.0
