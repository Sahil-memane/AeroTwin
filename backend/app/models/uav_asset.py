from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class UAVAsset(Base):
    __tablename__ = 'uav_assets'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tail_number = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, nullable=False, default='active')
