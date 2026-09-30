"""add_simulation_runs_table

Revision ID: 60490aef9043
Revises: d493f537b7f4
Create Date: 2026-09-29 13:31:00.596146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60490aef9043'
down_revision: Union[str, Sequence[str], None] = 'd493f537b7f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'simulation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('engine_id', sa.UUID(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('mission_id', sa.UUID(), nullable=True),
        sa.Column('environmental_profile', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['engine_id'], ['engines.id']),
        sa.ForeignKeyConstraint(['mission_id'], ['missions.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('simulation_runs')
