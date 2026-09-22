from sqlalchemy import Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class Mission(Base):
    __tablename__ = 'missions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uav_asset_id = Column(UUID(as_uuid=True), ForeignKey('uav_assets.id'), nullable=False)
    mission_type = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    environmental_profile = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default='scheduled')
