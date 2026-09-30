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
    # Accuracy-First Phase 3 — the temporal-consistency state machine's
    # classification for this row (app/services/fault_state.py). NULL on
    # rows written before this column existed.
    state = Column(String, nullable=True)
    # Share of the model's 32 input channels driven by measured telemetry when
    # this prediction was made (fault_adapter.input_coverage). Below
    # settings.FAULT_MIN_INPUT_COVERAGE the row is advisory and excluded from
    # Health Fusion. NULL on rows written before this column existed.
    input_coverage = Column(Float, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "fault_class IN ('No Failure', 'RC Failure', 'GPS Failure', 'Accelerometer Failure', "
            "'Gyro Failure', 'Compass Failure', 'Barometer Failure', 'Unknown / insufficient evidence')",
            name='valid_fault_class',
        ),
    )
