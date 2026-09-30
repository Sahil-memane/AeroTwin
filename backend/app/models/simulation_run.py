from sqlalchemy import Column, ForeignKey, DateTime, String, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class SimulationRun(Base):
    __tablename__ = 'simulation_runs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), nullable=False)
    mode = Column(String, nullable=False)  # 'replay' | 'what_if'
    mission_id = Column(UUID(as_uuid=True), ForeignKey('missions.id'), nullable=True)
    environmental_profile = Column(JSON, nullable=True)

    status = Column(String, nullable=False, default='queued')  # queued | running | completed | failed
    error = Column(String, nullable=True)
    # One entry per replayed/generated step: {ts, telemetry, rul, fault, bearing, aux, health_score}
    results = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
