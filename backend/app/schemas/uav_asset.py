from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class UAVAssetBase(BaseModel):
    tail_number: str
    status: str = 'active'

class UAVAssetCreate(UAVAssetBase):
    pass

class UAVAssetUpdate(BaseModel):
    tail_number: Optional[str] = None
    status: Optional[str] = None

class UAVAsset(UAVAssetBase):
    id: UUID
    
    class Config:
        from_attributes = True
