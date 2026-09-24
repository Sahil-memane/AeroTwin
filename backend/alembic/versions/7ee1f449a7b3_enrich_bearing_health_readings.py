"""enrich_bearing_health_readings

Adds full CNN output columns (class_id, class_label, severity_inches, confidence)
and drops the old generic severity_score column.
Also seeds the bearing_vibration_cnn entry into model_registry.

Revision ID: 7ee1f449a7b3
Revises: 060b6b7aa778
Create Date: 2026-09-24

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '7ee1f449a7b3'
down_revision: Union[str, Sequence[str], None] = '060b6b7aa778'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Enrich bearing_health_readings ────────────────────────────
    # Add new rich output columns
    op.add_column('bearing_health_readings',
        sa.Column('class_id', sa.Integer(), nullable=True))   # nullable during migration
    op.add_column('bearing_health_readings',
        sa.Column('class_label', sa.String(), nullable=True))
    op.add_column('bearing_health_readings',
        sa.Column('severity_inches', sa.Float(), nullable=True))
    op.add_column('bearing_health_readings',
        sa.Column('confidence', sa.Float(), nullable=True))

    # Back-fill existing rows (if any) so we can set NOT NULL
    op.execute("""
        UPDATE bearing_health_readings
        SET class_id    = 6,
            class_label = 'Normal',
            confidence  = 1.0
        WHERE class_id IS NULL
    """)

    # Now tighten NOT NULL on the new required columns
    op.alter_column('bearing_health_readings', 'class_id',   nullable=False)
    op.alter_column('bearing_health_readings', 'class_label',nullable=False)
    op.alter_column('bearing_health_readings', 'confidence', nullable=False)

    # Drop the old generic severity_score column (replaced by severity_inches)
    op.drop_column('bearing_health_readings', 'severity_score')

    # ── 2. Seed model_registry for bearing_vibration_cnn ─────────────
    op.execute("""
        INSERT INTO model_registry (id, model_name, version, is_active, validation_score, registered_at)
        VALUES (
            '00000000-0000-0000-0000-000000000006',
            'bearing_vibration_cnn',
            'v1.0.0',
            TRUE,
            0.9899,
            now()
        )
        ON CONFLICT (id) DO NOTHING
    """)


def downgrade() -> None:
    # Restore original schema
    op.add_column('bearing_health_readings',
        sa.Column('severity_score', sa.Float(), nullable=False, server_default='0.0'))
    op.drop_column('bearing_health_readings', 'confidence')
    op.drop_column('bearing_health_readings', 'severity_inches')
    op.drop_column('bearing_health_readings', 'class_label')
    op.drop_column('bearing_health_readings', 'class_id')

    op.execute("""
        DELETE FROM model_registry WHERE id = '00000000-0000-0000-0000-000000000006'
    """)
