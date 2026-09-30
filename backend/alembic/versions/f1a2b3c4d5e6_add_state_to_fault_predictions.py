"""add_state_to_fault_predictions

Accuracy-First Phase 3 (Fault Detection Reliability). `state` records
the temporal-consistency state machine's classification for this row
(NORMAL/ANOMALY_DETECTED/FAULT_SUSPECTED/FAULT_CONFIRMED/RECOVERED,
plus a reserved SENSOR_ANOMALY never assigned yet — see
app/services/fault_state.py) so Health Fusion can key its penalty off
a sustained pattern instead of one cycle's raw confidence. Additive
only — existing rows get NULL, which health_fusion.py's fallback
treats as "use the original confidence-only gate" (that IS what every
pre-Phase-3 row's actual historical behavior was).

Also widens the `valid_fault_class` check constraint to allow the new
"Unknown / insufficient evidence" abstention label (fault_service.py
returns this instead of a falsely-confident single class when stage-2
evidence is weak).

Revision ID: f1a2b3c4d5e6
Revises: 824a59f49dc4
Create Date: 2026-09-30 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = '824a59f49dc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fault_predictions', sa.Column('state', sa.String(), nullable=True))

    op.drop_constraint('valid_fault_class', 'fault_predictions', type_='check')
    op.create_check_constraint(
        'valid_fault_class',
        'fault_predictions',
        "fault_class IN ('No Failure', 'RC Failure', 'GPS Failure', 'Accelerometer Failure', "
        "'Gyro Failure', 'Compass Failure', 'Barometer Failure', 'Unknown / insufficient evidence')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('valid_fault_class', 'fault_predictions', type_='check')
    op.create_check_constraint(
        'valid_fault_class',
        'fault_predictions',
        "fault_class IN ('No Failure', 'RC Failure', 'GPS Failure', 'Accelerometer Failure', "
        "'Gyro Failure', 'Compass Failure', 'Barometer Failure')",
    )
    op.drop_column('fault_predictions', 'state')
