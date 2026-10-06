"""backfill session_bottles for single-bottle sessions

Revision ID: b0c9ba8d59ed
Revises: 02eeb3a2f266
Create Date: 2026-10-06 12:19:56.913602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0c9ba8d59ed'
down_revision: Union[str, Sequence[str], None] = '02eeb3a2f266'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sessions created before multi-lane support had exactly one bottle (lane 1)."""
    op.execute("""
        INSERT INTO session_bottles (session_id, machine_id, lane, refund_serial, mfg_serial, brand,
                                     status, reason, created_at, updated_at)
        SELECT s.id, s.machine_id, 1, s.refund_serial, s.mfg_serial, s.brand,
               CASE s.outcome WHEN 'ACCEPTED' THEN 'ACCEPTED'
                              WHEN 'RETURNED' THEN 'REJECTED'
                              ELSE 'CHECKING' END,
               CASE WHEN s.outcome = 'ACCEPTED' THEN NULL ELSE s.reason END,
               s.started_at, COALESCE(s.ended_at, s.started_at)
        FROM rvm_sessions s
        WHERE NOT EXISTS (SELECT 1 FROM session_bottles b WHERE b.session_id = s.id)
    """)


def downgrade() -> None:
    """Backfilled rows are indistinguishable from real ones; nothing to undo."""
