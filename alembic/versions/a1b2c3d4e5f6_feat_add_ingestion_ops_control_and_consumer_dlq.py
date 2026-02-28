"""feat: add ingestion ops control and consumer dlq audit tables

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-02-28 22:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_job_failures",
        sa.Column("failed_record_keys", sa.JSON(), nullable=True),
    )

    op.create_table(
        "ingestion_ops_control",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("mode", sa.String(), server_default="normal", nullable=False),
        sa.Column("replay_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replay_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO ingestion_ops_control "
            "(id, mode, replay_window_start, replay_window_end, updated_by) "
            "VALUES (1, 'normal', NULL, NULL, 'system_bootstrap')"
        )
    )

    op.create_table(
        "consumer_dlq_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("original_topic", sa.String(), nullable=False),
        sa.Column("consumer_group", sa.String(), nullable=False),
        sa.Column("dlq_topic", sa.String(), nullable=False),
        sa.Column("original_key", sa.String(), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("payload_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index(
        "ix_consumer_dlq_events_event_id",
        "consumer_dlq_events",
        ["event_id"],
        unique=True,
    )
    op.create_index(
        "ix_consumer_dlq_events_original_topic",
        "consumer_dlq_events",
        ["original_topic"],
        unique=False,
    )
    op.create_index(
        "ix_consumer_dlq_events_consumer_group",
        "consumer_dlq_events",
        ["consumer_group"],
        unique=False,
    )
    op.create_index(
        "ix_consumer_dlq_events_dlq_topic",
        "consumer_dlq_events",
        ["dlq_topic"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_consumer_dlq_events_dlq_topic", table_name="consumer_dlq_events")
    op.drop_index("ix_consumer_dlq_events_consumer_group", table_name="consumer_dlq_events")
    op.drop_index("ix_consumer_dlq_events_original_topic", table_name="consumer_dlq_events")
    op.drop_index("ix_consumer_dlq_events_event_id", table_name="consumer_dlq_events")
    op.drop_table("consumer_dlq_events")

    op.drop_table("ingestion_ops_control")
    op.drop_column("ingestion_job_failures", "failed_record_keys")
