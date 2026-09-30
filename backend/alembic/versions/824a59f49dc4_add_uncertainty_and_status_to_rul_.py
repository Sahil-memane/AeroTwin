"""add_uncertainty_and_status_to_rul_predictions

Accuracy-First Phase 2 (RUL Reliability & Uncertainty). `rul_lower`/
`rul_upper` were already computed by rul_service.push_reading() from a
real split-conformal calibration (conformal_q=22.82, alpha=0.1 — see
ml/training/rul_model/CMaps/saved_models/inference_config.json) but only
ever broadcast transiently over WebSocket, never persisted. `status`
records what the service itself observed at prediction time (VALID or
MODEL_ERROR — see rul_service.py's `_has_xgboost` mock-mode fallback);
INITIALIZING/INSUFFICIENT_DATA never get a row at all (no prediction was
made), and STALE is a read-time-relative concept computed by the API,
not stored. Additive only — existing rows get NULL.

Revision ID: 824a59f49dc4
Revises: af6549ea5279
Create Date: 2026-09-30 12:20:42.988324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '824a59f49dc4'
down_revision: Union[str, Sequence[str], None] = 'af6549ea5279'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('rul_predictions', sa.Column('rul_lower', sa.Float(), nullable=True))
    op.add_column('rul_predictions', sa.Column('rul_upper', sa.Float(), nullable=True))
    op.add_column('rul_predictions', sa.Column('status', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rul_predictions', 'status')
    op.drop_column('rul_predictions', 'rul_upper')
    op.drop_column('rul_predictions', 'rul_lower')
