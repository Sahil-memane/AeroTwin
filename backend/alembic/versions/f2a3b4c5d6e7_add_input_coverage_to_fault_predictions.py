"""add_input_coverage_to_fault_predictions

The fault model takes 32 UAV channels; the piston-engine adapter drives only
some of them from measured telemetry and fills the rest with fixed
placeholders, so the model's output can be confident while reflecting missing
sensors rather than engine state. This records, per prediction, the share of
input channels that were measured-driven so Health Fusion and the UI can tell
a trustworthy fault result from an advisory one. Additive and nullable —
historical rows stay NULL (treated as reliable, the legacy behavior).

Revision ID: f2a3b4c5d6e7
Revises: e7f8a9b0c1d2
Create Date: 2026-09-30 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fault_predictions', sa.Column('input_coverage', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('fault_predictions', 'input_coverage')
