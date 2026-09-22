from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class AlertBase(BaseModel):
    engine_id: UUID
    source: str
    severity: str
    message: str

class AlertCreate(AlertBase):
    pass

class Alert(AlertBase):
    id: UUID
    created_at: datetime
    is_acknowledged: bool
    acknowledged_by: Optional[UUID] = None
    acknowledged_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
