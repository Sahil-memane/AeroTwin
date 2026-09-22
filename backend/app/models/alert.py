from sqlalchemy import Column, ForeignKey, DateTime, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), nullable=False)
    source = Column(String, nullable=False)  # fault, rul, bearing, aux, physics, fusion
    severity = Column(String, nullable=False) # warning, critical
    message = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
