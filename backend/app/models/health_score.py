from sqlalchemy import Column, ForeignKey, DateTime, Float, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class HealthScore(Base):
    __tablename__ = 'health_scores'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)

    combined_score = Column(Float, nullable=False)
    contributing_factors = Column(JSON, nullable=False)
    # Accuracy-First Phase 5 — one-line summary of the single largest
    # contributing factor (health_fusion.py). NULL on rows written
    # before this column existed, and whenever there was nothing to
    # report (a perfect score with no contributing factors at all).
    primary_concern = Column(String, nullable=True)
