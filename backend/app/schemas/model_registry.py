from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class ModelRegistryBase(BaseModel):
    model_name: str
    version: str
    is_active: bool = False
    validation_score: Optional[float] = None

class ModelRegistryCreate(ModelRegistryBase):
    pass

class ModelRegistry(ModelRegistryBase):
    id: UUID
    registered_at: datetime
    
    class Config:
        from_attributes = True
