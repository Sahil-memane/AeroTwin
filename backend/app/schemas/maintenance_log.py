from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class MaintenanceLogBase(BaseModel):
    action_taken: str = Field(..., min_length=1, max_length=120)
    notes: Optional[str] = None

class MaintenanceLogCreate(MaintenanceLogBase):
    pass

class MaintenanceLog(MaintenanceLogBase):
    id: UUID
    engine_id: UUID
    user_id: UUID
    logged_at: datetime

    class Config:
        from_attributes = True
