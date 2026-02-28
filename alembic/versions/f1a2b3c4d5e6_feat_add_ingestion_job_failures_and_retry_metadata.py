"""feat: add ingestion job failure history and retry metadata

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-02-28 23:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("request_payload", sa.JSON(), nullable=True))
    op.add_column(
        "ingestion_jobs",
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("ingestion_jobs", sa.Column("last_retried_at", sa.DateTime(timezone=True)))

    op.create_table(
        "ingestion_job_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("failure_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("failure_phase", sa.String(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=False),
        sa.Column(
            "failed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.job_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("failure_id"),
    )
    op.create_index(
        "ix_ingestion_job_failures_failure_id",
        "ingestion_job_failures",
        ["failure_id"],
        unique=True,
    )
    op.create_index(
        "ix_ingestion_job_failures_job_id",
        "ingestion_job_failures",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_job_failures_job_id", table_name="ingestion_job_failures")
    op.drop_index("ix_ingestion_job_failures_failure_id", table_name="ingestion_job_failures")
    op.drop_table("ingestion_job_failures")

    op.drop_column("ingestion_jobs", "last_retried_at")
    op.drop_column("ingestion_jobs", "retry_count")
    op.drop_column("ingestion_jobs", "request_payload")
