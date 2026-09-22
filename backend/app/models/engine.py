from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class Engine(Base):
    __tablename__ = 'engines'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    serial_number = Column(String, unique=True, index=True, nullable=False)
    uav_asset_id = Column(UUID(as_uuid=True), ForeignKey('uav_assets.id'), nullable=True)
    status = Column(String, nullable=False, default='operational')
