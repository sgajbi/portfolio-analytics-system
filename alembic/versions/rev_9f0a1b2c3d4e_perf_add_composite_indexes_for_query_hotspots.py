"""perf: add composite indexes for query hotspots

Revision ID: 9f0a1b2c3d4e
Revises: e1f2a3b4c6d7
Create Date: 2026-03-01 23:05:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f0a1b2c3d4e"
down_revision: Union[str, None] = "e1f2a3b4c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_position_history_portfolio_security_epoch_date",
        "position_history",
        ["portfolio_id", "security_id", "epoch", "position_date"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_composition_series_benchmark_effective_window",
        "benchmark_composition_series",
        ["benchmark_id", "composition_effective_from", "composition_effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_index_price_series_index_id_series_date",
        "index_price_series",
        ["index_id", "series_date"],
        unique=False,
    )
    op.create_index(
        "ix_index_return_series_index_id_series_date",
        "index_return_series",
        ["index_id", "series_date"],
        unique=False,
    )
    op.create_index(
        "ix_benchmark_return_series_benchmark_id_series_date",
        "benchmark_return_series",
        ["benchmark_id", "series_date"],
        unique=False,
    )
    op.create_index(
        "ix_risk_free_series_currency_series_date",
        "risk_free_series",
        ["series_currency", "series_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_risk_free_series_currency_series_date",
        table_name="risk_free_series",
    )
    op.drop_index(
        "ix_benchmark_return_series_benchmark_id_series_date",
        table_name="benchmark_return_series",
    )
    op.drop_index(
        "ix_index_return_series_index_id_series_date",
        table_name="index_return_series",
    )
    op.drop_index(
        "ix_index_price_series_index_id_series_date",
        table_name="index_price_series",
    )
    op.drop_index(
        "ix_benchmark_composition_series_benchmark_effective_window",
        table_name="benchmark_composition_series",
    )
    op.drop_index(
        "ix_position_history_portfolio_security_epoch_date",
        table_name="position_history",
    )
