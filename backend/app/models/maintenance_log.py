from sqlalchemy import Column, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class MaintenanceLog(Base):
    __tablename__ = 'maintenance_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    logged_at = Column(DateTime, server_default=func.now())
    notes = Column(String, nullable=False)
