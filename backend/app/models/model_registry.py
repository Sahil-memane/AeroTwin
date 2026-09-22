from sqlalchemy import Column, String, Boolean, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class ModelRegistry(Base):
    __tablename__ = 'model_registry'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String, index=True, nullable=False)  # fault_model, rul_model, bearing_model, aux_model
    version = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    validation_score = Column(Float, nullable=True)
    registered_at = Column(DateTime, server_default=func.now())
