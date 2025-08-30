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
    
    # This mock is now used by get_cashflows_for_period
    mock_result.scalars.return_value.all.return_value = ["cashflow_1", "cashflow_2"] 
    
    mock_result.all.return_value = [("snapshot_1", "instrument_1"), ("snapshot_2", "instrument_2")]
    mock_result.scalar_one_or_none.return_value = 1234.56

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

async def test_get_cashflows_for_period_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and date range
    WHEN get_cashflows_for_period is called
    THEN it should construct a query that selects all cashflows for the current epoch.
    """
    # ACT
    await repository.get_cashflows_for_period("P1", date(2025, 1, 1), date(2025, 8, 29))
    
    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT cashflows.id" in compiled_query
    assert "GROUP BY" not in compiled_query
    assert "JOIN position_state" in compiled_query
    assert "cashflows.epoch = coalesce((SELECT max(position_state.epoch)" in compiled_query
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

async def test_get_total_unrealized_pnl_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and as_of_date
    WHEN get_total_unrealized_pnl is called
    THEN it should construct a query that sums unrealized_gain_loss from the latest snapshots.
    """
    # ACT
    await repository.get_total_unrealized_pnl("P1", date(2025, 8, 29))

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "SELECT sum(ranked_snapshots.unrealized_gain_loss)" in compiled_query
    assert "FROM (SELECT daily_position_snapshots.unrealized_gain_loss" in compiled_query
    assert "row_number() over" in compiled_query.lower()
    assert "WHERE ranked_snapshots.rn = 1" in compiled_query
    assert "ranked_snapshots.quantity > 0" in compiled_query