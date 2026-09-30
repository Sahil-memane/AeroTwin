from sqlalchemy import Column, ForeignKey, DateTime, Float, String
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

    # Operating conditions the RUL adapter and physics baseline use when the
    # source provides them (the simulator/edge agent do). NULL for rows
    # written before these columns existed, and for sources that don't send
    # them — consumers must then fall back exactly as live ingestion does
    # for a payload without them (never an invented value).
    throttle = Column(Float, nullable=True)
    altitude_m = Column(Float, nullable=True)

    # Accuracy-First Phase 1 — the validate_payload() classification this
    # reading received (VALID/STALE/SUSPICIOUS) at ingest time. NULL for
    # every row written before this column existed — treat NULL as
    # "unknown," not as VALID, when reading historical data.
    quality_status = Column(String, nullable=True)
