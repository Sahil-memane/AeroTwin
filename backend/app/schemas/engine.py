from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class EngineBase(BaseModel):
    serial_number: str
    uav_asset_id: Optional[UUID] = None
    status: str = 'operational'

class EngineCreate(EngineBase):
    pass

class EngineUpdate(BaseModel):
    serial_number: Optional[str] = None
    uav_asset_id: Optional[UUID] = None
    status: Optional[str] = None

class Engine(EngineBase):
    id: UUID
    
    class Config:
        from_attributes = True
