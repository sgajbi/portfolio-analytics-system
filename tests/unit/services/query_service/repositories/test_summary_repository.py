# tests/unit/services/query_service/repositories/test_summary_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.summary_repository import SummaryRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = [("snapshot_1", "instrument_1"), ("snapshot_2", "instrument_2")]
    # Allow scalar results for P&L and mapping results for cashflows
    mock_result.scalar_one_or_none.return_value = 1234.56
    mock_result.mappings.return_value = [{"classification": "CASHFLOW_IN", "total_amount": 5000}]
    session.execute = AsyncMock(return_value=mock_result)
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> SummaryRepository:
    """Provides an instance of the repository with a mock session."""
    return SummaryRepository(mock_db_session)

async def test_get_wealth_and_allocation_data_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and as_of_date
    WHEN get_wealth_and_allocation_data is called
    THEN it should construct a query that correctly joins snapshots, state, and instruments,
         and uses a window function to find the latest record for the current epoch.
    """
    # ACT
    await repository.get_wealth_and_allocation_data(
        portfolio_id="P1",
        as_of_date=date(2025, 8, 29)
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "FROM daily_position_snapshots" in compiled_query
    assert "JOIN position_state ON" in compiled_query
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled_query
    assert "JOIN instruments ON" in compiled_query
    assert "daily_position_snapshots.portfolio_id = 'P1'" in compiled_query
    assert "daily_position_snapshots.date <= '2025-08-29'" in compiled_query
    assert "row_number() over" in compiled_query.lower()
    assert "partition by daily_position_snapshots.security_id" in compiled_query.lower()
    assert "WHERE ranked_snapshots.rn = 1" in compiled_query
    assert "ranked_snapshots.quantity > 0" in compiled_query

async def test_get_cashflow_summary_data_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and date range
    WHEN get_cashflow_summary_data is called
    THEN it should construct a query that aggregates cashflows by classification for the current epoch.
    """
    # ACT
    await repository.get_cashflow_summary_data("P1", date(2025, 1, 1), date(2025, 8, 29))
    
    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT cashflows.classification, sum(cashflows.amount) AS total_amount" in compiled_query
    assert "JOIN position_state" in compiled_query
    assert "cashflows.epoch = coalesce((SELECT max(position_state.epoch)" in compiled_query
    assert "GROUP BY cashflows.classification" in compiled_query
    assert "cashflows.cashflow_date BETWEEN '2025-01-01' AND '2025-08-29'" in compiled_query

async def test_get_realized_pnl_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and date range
    WHEN get_realized_pnl is called
    THEN it should construct a query that sums realized_gain_loss from the transactions table.
    """
    # ACT
    await repository.get_realized_pnl("P1", date(2025, 1, 1), date(2025, 8, 29))

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "SELECT sum(transactions.realized_gain_loss)" in compiled_query
    assert "FROM transactions" in compiled_query
    assert "WHERE transactions.portfolio_id = 'P1'" in compiled_query
    assert "date(transactions.transaction_date) BETWEEN '2025-01-01' AND '2025-08-29'" in compiled_query