"""add_action_taken_to_maintenance_logs

Revision ID: 5202add01c5c
Revises: c5555a973549
Create Date: 2026-09-29 04:31:11.217788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5202add01c5c'
down_revision: Union[str, Sequence[str], None] = 'c5555a973549'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('maintenance_logs',
        sa.Column('action_taken', sa.String(), nullable=True))  # nullable during migration

    # Back-fill existing rows (if any) from the old required `notes` field
    op.execute("""
        UPDATE maintenance_logs
        SET action_taken = notes
        WHERE action_taken IS NULL
    """)

    op.alter_column('maintenance_logs', 'action_taken', nullable=False)
    op.alter_column('maintenance_logs', 'notes', nullable=True)


def downgrade() -> None:
    op.alter_column('maintenance_logs', 'notes', nullable=False)
    op.drop_column('maintenance_logs', 'action_taken')
