from pydantic import BaseModel
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime

class MissionBase(BaseModel):
    uav_asset_id: UUID
    mission_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    environmental_profile: Optional[Dict[str, Any]] = None
    status: str = 'scheduled'

class MissionCreate(MissionBase):
    pass

class MissionUpdate(BaseModel):
    status: Optional[str] = None
    end_time: Optional[datetime] = None

class Mission(MissionBase):
    id: UUID
    
    class Config:
        from_attributes = True
