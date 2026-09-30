"""add_physics_deviation_readings

Accuracy-First Phase 4 (Lightweight Physics Baseline, pulled forward
from the source document's Tier 2). New table only — persists the
already-built Otto-cycle physics model's expected-vs-measured
comparison for every live reading, one row per (engine, ts, parameter),
covering the 5 channels the solver computes (CHT, EGT, oil pressure,
oil temp, fuel flow). Nothing else changes.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-30 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'physics_deviation_readings',
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('engine_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parameter', sa.String(), nullable=False),
        sa.Column('expected', sa.Float(), nullable=False),
        sa.Column('measured', sa.Float(), nullable=False),
        sa.Column('residual', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['engine_id'], ['engines.id']),
        sa.PrimaryKeyConstraint('ts', 'engine_id', 'parameter'),
    )
    # No standalone engine_id index — matches every other prediction
    # table in this schema (rul_predictions, fault_predictions, …), none
    # of which index engine_id separately from their composite PK either,
    # despite the identical "filter by engine_id, order by ts" query
    # pattern (see health_fusion.py's `_latest()` helper).


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('physics_deviation_readings')
