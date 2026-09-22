import os
import re

base_dir = r"e:\Projects\AeroTwin"

tree_str = """
frontend/
├── src/
│   ├── components/
│   │   ├── FaultAlertBanner.tsx
│   │   ├── RulTrendChart.tsx
│   │   ├── BearingHealthGauge.tsx
│   │   └── HealthScoreGauge.tsx
│   ├── pages/
│   ├── hooks/
│   ├── services/
│   │   └── apiClient.ts
│   ├── store/
│   ├── types/
│   └── App.tsx
├── public/
├── tests/
├── .env.example
└── package.json
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── telemetry.py
│   │       ├── engines.py
│   │       ├── uav_assets.py
│   │       ├── users.py
│   │       ├── faults.py
│   │       ├── rul.py
│   │       ├── bearing.py
│   │       ├── dashboard.py
│   │       ├── missions.py
│   │       ├── simulation.py
│   │       ├── alerts.py
│   │       ├── maintenance.py
│   │       └── models.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── logging.py
│   ├── models/
│   │   ├── user.py
│   │   ├── uav_asset.py
│   │   ├── engine.py
│   │   ├── mission.py
│   │   ├── telemetry_reading.py
│   │   ├── fault_prediction.py
│   │   ├── rul_prediction.py
│   │   ├── bearing_health_reading.py
│   │   ├── aux_prediction.py
│   │   ├── maintenance_log.py
│   │   ├── alert.py
│   │   └── model_registry.py
│   ├── schemas/
│   ├── services/
│   │   ├── ingestion.py
│   │   ├── health_fusion.py
│   │   └── alert_engine.py
│   ├── ws/
│   │   ├── connection_manager.py
│   │   └── telemetry_broadcaster.py
│   ├── db/
│   │   ├── session.py
│   │   └── base.py
│   └── main.py
├── tests/
│   ├── unit/
│   └── integration/
├── alembic/
│   └── versions/
├── .env.example
└── requirements.txt
ml/
├── data/
│   ├── raw/
│   └── processed/
├── notebooks/
├── training/
│   ├── fault_model/
│   │   ├── preprocess.py
│   │   ├── train.py
│   │   └── export_onnx.py
│   ├── rul_model/
│   │   ├── preprocess.py
│   │   ├── train.py
│   │   └── export_onnx.py
│   ├── bearing_model/
│   │   ├── fft_features.py
│   │   ├── train.py
│   │   └── export_onnx.py
│   ├── aux_model/
│   │   ├── pretrain.py
│   │   ├── finetune.py
│   │   └── export_onnx.py
│   └── physics_model/
│       └── otto_cycle_solver.py
├── models/
│   ├── fault_model/
│   ├── rul_model/
│   ├── bearing_model/
│   └── aux_model/
├── evaluation/
└── requirements.txt
simulation/
├── mission_profiles/
├── replay_engine/
└── scenario_generator/
edge/
├── can_interface/
├── inference/
└── telemetry_publisher/
    └── simulate.py
infra/
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── Dockerfile.ml-inference
│   └── docker-compose.yml
└── nginx/
docs/
├── architecture/
├── api/
├── dataset-guide/
├── decisions-log.md
└── devlog.md
.github/
├── workflows/
├── ISSUE_TEMPLATE/
└── pull_request_template.md
.env.example
README.md
LICENSE
"""

def scaffold():
    lines = tree_str.strip().split("\n")
    path_stack = []
    
    for line in lines:
        if not line.strip():
            continue
            
        # Count the leading characters to determine depth
        match = re.match(r'^([│├└─\s]*)(.*)$', line)
        if not match:
            continue
            
        prefix, name = match.groups()
        # Each level of depth in the tree is usually 4 characters: e.g. '├── ' or '│   '
        # Let's just calculate depth by length of prefix divided by 4
        # A more robust way is to replace special chars with spaces and count spaces
        prefix = prefix.replace('├──', '   ').replace('└──', '   ').replace('│', ' ').replace('─', ' ')
        depth = len(prefix) // 4
        
        # Clean up the name (remove trailing comments)
        name = name.split('#')[0].strip()
        
        path_stack = path_stack[:depth]
        path_stack.append(name)
        
        full_path = os.path.join(base_dir, *path_stack)
        
        if name.endswith('/') or not ('.' in name or name in ['LICENSE', 'Dockerfile.backend', 'Dockerfile.frontend', 'Dockerfile.ml-inference']):
            # It's a directory (assuming if it doesn't have an extension and isn't LICENSE/Dockerfile, it's a dir, unless explicitly ending in /)
            if not name.endswith('/') and '.' in name:
                # wait, if it has a dot it's a file, we already checked that.
                pass
            os.makedirs(full_path, exist_ok=True)
            print(f"Created directory: {full_path}")
        else:
            # It's a file
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            if not os.path.exists(full_path):
                with open(full_path, 'w', encoding='utf-8') as f:
                    pass
                print(f"Created file: {full_path}")

if __name__ == "__main__":
    scaffold()
