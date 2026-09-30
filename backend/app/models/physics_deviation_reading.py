from sqlalchemy import Column, ForeignKey, DateTime, String, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class PhysicsDeviationReading(Base):
    """
    Accuracy-First Phase 4 — one row per (engine, ts, parameter): the
    Otto-cycle physics model's expected value for that channel next to
    what was actually measured, so "physics vs AI" is a real, persisted
    comparison rather than a number computed and discarded.
    """
    __tablename__ = 'physics_deviation_readings'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    parameter = Column(String, primary_key=True, nullable=False)  # cht|egt|oil_pressure|oil_temp|fuel_flow

    expected = Column(Float, nullable=False)
    measured = Column(Float, nullable=False)
    residual = Column(Float, nullable=False)  # measured - expected
    status = Column(String, nullable=False)   # CONSISTENT|ELEVATED|REVIEW|ANOMALY
    method = Column(String, nullable=False, default="documented_baseline_v1")
