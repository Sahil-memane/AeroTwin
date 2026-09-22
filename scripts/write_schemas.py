import os

base_path = r"e:\Projects\AeroTwin\backend\app\schemas"

schemas = {
    "user.py": """from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    role: str
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserInDBBase(UserBase):
    id: UUID
    
    class Config:
        from_attributes = True

class User(UserInDBBase):
    pass
""",
    "uav_asset.py": """from pydantic import BaseModel
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
""",
    "engine.py": """from pydantic import BaseModel
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
""",
    "mission.py": """from pydantic import BaseModel
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
""",
    "telemetry.py": """from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime

class TelemetryIngestBase(BaseModel):
    engine_id: UUID
    mission_id: Optional[UUID] = None
    ts: datetime
    rpm: float
    cht: float
    egt: float
    oil_pressure: float
    oil_temp: float
    fuel_flow: float
    vibration_x: Optional[float] = None
    vibration_y: Optional[float] = None
    vibration_z: Optional[float] = None

class TelemetryReading(TelemetryIngestBase):
    class Config:
        from_attributes = True
""",
    "predictions.py": """from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class FaultPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    fault_class: str
    confidence: float
    
    class Config:
        from_attributes = True

class RulPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    rul_hours: float
    degradation_index: float
    
    class Config:
        from_attributes = True

class BearingHealthReading(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    fault_location: str
    severity_score: float
    
    class Config:
        from_attributes = True

class AuxPrediction(BaseModel):
    ts: datetime
    engine_id: UUID
    model_version_id: UUID
    aux_score: float
    
    class Config:
        from_attributes = True
""",
    "maintenance_log.py": """from pydantic import BaseModel
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
""",
    "alert.py": """from pydantic import BaseModel
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
""",
    "model_registry.py": """from pydantic import BaseModel
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
"""
}

def write_schemas():
    os.makedirs(base_path, exist_ok=True)
    
    for filename, content in schemas.items():
        full_path = os.path.join(base_path, filename)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
            
    # Also write __init__.py to export them all
    init_content = "\\n".join([f"from .{filename[:-3]} import *" for filename in schemas.keys() if filename != "__init__.py"])
    with open(os.path.join(base_path, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(init_content.strip() + "\\n")
        
    print("All schemas written successfully.")

if __name__ == "__main__":
    write_schemas()
