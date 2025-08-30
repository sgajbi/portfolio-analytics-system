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
    THEN it should construct a query that correctly joins snapshots, state, and instruments.
    """
    await repository.get_wealth_and_allocation_data("P1", date(2025, 8, 29))
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "FROM daily_position_snapshots" in compiled_query
    assert "JOIN position_state ON" in compiled_query
    assert "daily_position_snapshots.epoch = position_state.epoch" in compiled_query
    assert "JOIN instruments ON" in compiled_query
    assert "row_number() over" in compiled_query.lower()

async def test_get_cashflows_for_period_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and date range
    WHEN get_cashflows_for_period is called
    THEN it should construct a query that eagerly loads the related transaction data.
    """
    await repository.get_cashflows_for_period("P1", date(2025, 1, 1), date(2025, 8, 29))
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    # --- FIX: Make assertion robust ---
    # Check that the query selects columns from cashflows and performs the required joins.
    assert "SELECT" in compiled_query
    assert "cashflows.id" in compiled_query
    assert "JOIN transactions ON transactions.transaction_id = cashflows.transaction_id" in compiled_query
    assert "JOIN position_state" in compiled_query
    # --- END FIX ---

async def test_get_realized_pnl_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and date range
    WHEN get_realized_pnl is called
    THEN it should construct a query that sums realized_gain_loss from the transactions table.
    """
    await repository.get_realized_pnl("P1", date(2025, 1, 1), date(2025, 8, 29))
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SELECT sum(transactions.realized_gain_loss)" in compiled_query
    assert "WHERE transactions.portfolio_id = 'P1'" in compiled_query

async def test_get_total_unrealized_pnl_query(repository: SummaryRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id and as_of_date
    WHEN get_total_unrealized_pnl is called
    THEN it should construct a query that sums unrealized_gain_loss from the latest snapshots.
    """
    await repository.get_total_unrealized_pnl("P1", date(2025, 8, 29))
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "SELECT sum(ranked_snapshots.unrealized_gain_loss)" in compiled_query
    assert "row_number() over" in compiled_query.lower()