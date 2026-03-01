"""feat: add consumer dlq replay audit table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 10:35:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consumer_dlq_replay_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("replay_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("replay_fingerprint", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("endpoint", sa.String(), nullable=True),
        sa.Column("replay_status", sa.String(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("replay_reason", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_replay_id",
        "consumer_dlq_replay_audit",
        ["replay_id"],
        unique=True,
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_event_id",
        "consumer_dlq_replay_audit",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_replay_fingerprint",
        "consumer_dlq_replay_audit",
        ["replay_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_replay_status",
        "consumer_dlq_replay_audit",
        ["replay_status"],
        unique=False,
    )
    op.create_index(
        "ix_consumer_dlq_replay_audit_job_id",
        "consumer_dlq_replay_audit",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_consumer_dlq_replay_audit_job_id", table_name="consumer_dlq_replay_audit")
    op.drop_index(
        "ix_consumer_dlq_replay_audit_replay_status", table_name="consumer_dlq_replay_audit"
    )
    op.drop_index(
        "ix_consumer_dlq_replay_audit_replay_fingerprint", table_name="consumer_dlq_replay_audit"
    )
    op.drop_index("ix_consumer_dlq_replay_audit_event_id", table_name="consumer_dlq_replay_audit")
    op.drop_index("ix_consumer_dlq_replay_audit_replay_id", table_name="consumer_dlq_replay_audit")
    op.drop_table("consumer_dlq_replay_audit")
