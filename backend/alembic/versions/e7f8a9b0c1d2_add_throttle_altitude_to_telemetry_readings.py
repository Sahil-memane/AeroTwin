"""add_throttle_altitude_to_telemetry_readings

The RUL adapter (piston_to_cmapss) and the physics baseline both use
throttle and altitude_m when the source supplies them. Live MQTT ingestion
passed them through in memory but never persisted them, so anything that
re-reads stored telemetry (mission replay, the parameter What-If window)
ran RUL on adapter defaults and the What-If baseline could not reproduce
the live score. Additive and nullable — historical rows stay NULL and
consumers must treat NULL as "not provided", never as 0.

Revision ID: e7f8a9b0c1d2
Revises: b1c2d3e4f5a6
Create Date: 2026-09-30 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('telemetry_readings', sa.Column('throttle', sa.Float(), nullable=True))
    op.add_column('telemetry_readings', sa.Column('altitude_m', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('telemetry_readings', 'altitude_m')
    op.drop_column('telemetry_readings', 'throttle')
