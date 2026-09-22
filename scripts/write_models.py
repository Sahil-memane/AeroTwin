import os

base_path = r"e:\Projects\AeroTwin\backend\app\models"

models = {
    "user.py": """from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # operator, maintenance_engineer, program_manager, admin
    is_active = Column(Boolean, default=True)
""",
    "uav_asset.py": """from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class UAVAsset(Base):
    __tablename__ = 'uav_assets'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tail_number = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, nullable=False, default='active')
""",
    "engine.py": """from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class Engine(Base):
    __tablename__ = 'engines'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    serial_number = Column(String, unique=True, index=True, nullable=False)
    uav_asset_id = Column(UUID(as_uuid=True), ForeignKey('uav_assets.id'), nullable=True)
    status = Column(String, nullable=False, default='operational')
""",
    "mission.py": """from sqlalchemy import Column, String, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base import Base

class Mission(Base):
    __tablename__ = 'missions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uav_asset_id = Column(UUID(as_uuid=True), ForeignKey('uav_assets.id'), nullable=False)
    mission_type = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    environmental_profile = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default='scheduled')
""",
    "telemetry_reading.py": """from sqlalchemy import Column, ForeignKey, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class TelemetryReading(Base):
    __tablename__ = 'telemetry_readings'

    # TimescaleDB hypertable on ts
    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey('missions.id'), nullable=True)
    
    rpm = Column(Float, nullable=False)
    cht = Column(Float, nullable=False)
    egt = Column(Float, nullable=False)
    oil_pressure = Column(Float, nullable=False)
    oil_temp = Column(Float, nullable=False)
    fuel_flow = Column(Float, nullable=False)
    vibration_x = Column(Float, nullable=True)
    vibration_y = Column(Float, nullable=True)
    vibration_z = Column(Float, nullable=True)
""",
    "model_registry.py": """from sqlalchemy import Column, String, Boolean, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class ModelRegistry(Base):
    __tablename__ = 'model_registry'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String, index=True, nullable=False)  # fault_model, rul_model, bearing_model, aux_model
    version = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    validation_score = Column(Float, nullable=True)
    registered_at = Column(DateTime, server_default=func.now())
""",
    "fault_prediction.py": """from sqlalchemy import Column, ForeignKey, DateTime, String, Float, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class FaultPrediction(Base):
    __tablename__ = 'fault_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    fault_class = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)

    __table_args__ = (
        CheckConstraint("fault_class IN ('No failure', 'RC', 'GPS', 'Aileron', 'Elevator', 'Rudder', 'Engine failure')", name='valid_fault_class'),
    )
""",
    "rul_prediction.py": """from sqlalchemy import Column, ForeignKey, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class RulPrediction(Base):
    __tablename__ = 'rul_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    rul_hours = Column(Float, nullable=False)
    degradation_index = Column(Float, nullable=False)
""",
    "bearing_health_reading.py": """from sqlalchemy import Column, ForeignKey, DateTime, String, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class BearingHealthReading(Base):
    __tablename__ = 'bearing_health_readings'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    fault_location = Column(String, nullable=False)
    severity_score = Column(Float, nullable=False)
""",
    "aux_prediction.py": """from sqlalchemy import Column, ForeignKey, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class AuxPrediction(Base):
    __tablename__ = 'aux_predictions'

    ts = Column(DateTime, primary_key=True, nullable=False)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), primary_key=True, nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_registry.id'), nullable=False)
    
    aux_score = Column(Float, nullable=False)
""",
    "maintenance_log.py": """from sqlalchemy import Column, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class MaintenanceLog(Base):
    __tablename__ = 'maintenance_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    logged_at = Column(DateTime, server_default=func.now())
    notes = Column(String, nullable=False)
""",
    "alert.py": """from sqlalchemy import Column, ForeignKey, DateTime, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.sql import func
from app.db.base import Base

class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engine_id = Column(UUID(as_uuid=True), ForeignKey('engines.id'), nullable=False)
    source = Column(String, nullable=False)  # fault, rul, bearing, aux, physics, fusion
    severity = Column(String, nullable=False) # warning, critical
    message = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
"""
}

def write_models():
    os.makedirs(base_path, exist_ok=True)
    
    for filename, content in models.items():
        full_path = os.path.join(base_path, filename)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")
            
    # Also write __init__.py to export them all
    init_content = "\\n".join([f"from .{filename[:-3]} import *" for filename in models.keys() if filename != "__init__.py"])
    init_content = "from app.db.base import Base\\n" + init_content
    with open(os.path.join(base_path, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(init_content.strip() + "\\n")
        
    print("All models written successfully.")

if __name__ == "__main__":
    write_models()
