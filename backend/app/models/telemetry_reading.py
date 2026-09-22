from sqlalchemy import Column, ForeignKey, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class TelemetryReading(Base):
    __tablename__ = 'telemetry_readings'

    # TimescaleDB hypertable on ts
    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey('missions.id'), nullable=True)
    
    rpm = Column(Float, nullable=False)
    cht = Column(Float, nullable=False)
    egt = Column(Float, nullable=False)
    oil_pressure = Column(Float, nullable=False)
    oil_temp = Column(Float, nullable=False)
    fuel_flow = Column(Float, nullable=False)
    vibration_x = Column(Float, nullable=True)
    vibration_y = Column(Float, nullable=True)
    vibration_z = Column(Float, nullable=True)
