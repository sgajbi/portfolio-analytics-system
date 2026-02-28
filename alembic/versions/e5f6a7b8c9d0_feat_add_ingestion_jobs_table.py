"""feat: add ingestion jobs table for API-first ingestion operations

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-28 21:36:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="accepted", nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )
    op.create_index("ix_ingestion_jobs_job_id", "ingestion_jobs", ["job_id"], unique=True)
    op.create_index("ix_ingestion_jobs_endpoint", "ingestion_jobs", ["endpoint"], unique=False)
    op.create_index(
        "ix_ingestion_jobs_entity_type", "ingestion_jobs", ["entity_type"], unique=False
    )
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)
    op.create_index(
        "ix_ingestion_jobs_idempotency_key",
        "ingestion_jobs",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_idempotency_key", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_status", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_entity_type", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_endpoint", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_job_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
