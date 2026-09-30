"""add_health_scores_table

Revision ID: d493f537b7f4
Revises: 5202add01c5c
Create Date: 2026-09-29 10:59:22.677472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd493f537b7f4'
down_revision: Union[str, Sequence[str], None] = '5202add01c5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'health_scores',
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('engine_id', sa.UUID(), nullable=False),
        sa.Column('combined_score', sa.Float(), nullable=False),
        sa.Column('contributing_factors', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['engine_id'], ['engines.id']),
        sa.PrimaryKeyConstraint('ts', 'engine_id'),
    )


def downgrade() -> None:
    op.drop_table('health_scores')
