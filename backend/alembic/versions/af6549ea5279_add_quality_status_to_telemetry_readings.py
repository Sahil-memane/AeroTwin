"""add_quality_status_to_telemetry_readings

Accuracy-First Phase 1 (Data Quality Layer): persists the
validate_payload() classification (VALID/STALE/SUSPICIOUS) each reading
received at ingest time, so data quality is visible after the fact
instead of only in transient logs. Additive only — existing rows get
NULL, which callers must treat as "unknown," not "VALID."

Revision ID: af6549ea5279
Revises: 60490aef9043
Create Date: 2026-09-30 12:14:59.010146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af6549ea5279'
down_revision: Union[str, Sequence[str], None] = '60490aef9043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('telemetry_readings', sa.Column('quality_status', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('telemetry_readings', 'quality_status')
