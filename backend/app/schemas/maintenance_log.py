from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class MaintenanceLogBase(BaseModel):
    engine_id: UUID
    notes: str

class MaintenanceLogCreate(MaintenanceLogBase):
    pass

class MaintenanceLog(MaintenanceLogBase):
    id: UUID
    user_id: UUID
    logged_at: datetime
    
    class Config:
        from_attributes = True
