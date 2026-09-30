"""seed_missing_model_registry_rows

The bearing model was seeded in 7ee1f449a7b3, but RUL/Fault/Aux never were.
ingestion.py hardcodes their model_version_id as the well-known UUIDs
...0003 (rul), ...0004 (fault), ...0005 (aux) — without matching rows in
model_registry, every RUL/Fault/Aux prediction fails its FK constraint on
save (silently, since ingestion.py logs and swallows the exception). This
seeds the missing three rows using each model's real held-out validation
metric reported in docs/files/ (Fault: 94.48% overall accuracy from
UAV_Sensor_Fault_Detection_Documentation.md; RUL: R^2 = 0.8992 from
RUL_Model_Integration_Documentation.md; Aux: 0.989 test accuracy for the
selected Random_Forest_Balanced model from
ml/training/aux_model/final_model/binary_failure_metrics.json).

Revision ID: c5555a973549
Revises: 7ee1f449a7b3
Create Date: 2026-09-29 04:20:27.221496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5555a973549'
down_revision: Union[str, Sequence[str], None] = '7ee1f449a7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO model_registry (id, model_name, version, is_active, validation_score, registered_at)
        VALUES
            ('00000000-0000-0000-0000-000000000003', 'rul_xgb_base',             'v1.0.0', TRUE, 0.8992, now()),
            ('00000000-0000-0000-0000-000000000004', 'fault_lgb_2stage',         'v1.0.0', TRUE, 0.9448, now()),
            ('00000000-0000-0000-0000-000000000005', 'aux_predictive_maintenance','v1.0.0', TRUE, 0.9890, now())
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM model_registry WHERE id IN (
            '00000000-0000-0000-0000-000000000003',
            '00000000-0000-0000-0000-000000000004',
            '00000000-0000-0000-0000-000000000005'
        )
    """)
