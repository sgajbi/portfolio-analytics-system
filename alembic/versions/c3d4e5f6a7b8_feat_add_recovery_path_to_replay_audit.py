"""feat: add recovery_path to replay audit

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-01 11:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consumer_dlq_replay_audit",
        sa.Column(
            "recovery_path",
            sa.String(),
            nullable=False,
            server_default="consumer_dlq_replay",
        ),
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_recovery_path",
        "consumer_dlq_replay_audit",
        ["recovery_path"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_consumer_dlq_replay_audit_recovery_path",
        table_name="consumer_dlq_replay_audit",
    )
    op.drop_column("consumer_dlq_replay_audit", "recovery_path")
