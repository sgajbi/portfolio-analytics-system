# tests/unit/services/query_service/repositories/test_position_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    
    # Configure mock to handle different return types
    mock_result.all.return_value = [("mock_snapshot", "mock_name")] 
    mock_result.scalars.return_value.all.return_value = ["mock_history_1", "mock_history_2"]
    session.execute.return_value = mock_result
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PositionRepository:
    """Provides an instance of the repository with a mock session."""
    return PositionRepository(mock_db_session)

async def test_get_position_history_with_filters(repository: PositionRepository, mock_db_session: AsyncMock):
    """
    GIVEN various filters
    WHEN get_position_history_by_security is called
    THEN it should construct a SELECT statement with the correct WHERE and ORDER BY clauses.
    """
    # ACT
    await repository.get_position_history_by_security(
        portfolio_id="P1",
        security_id="S1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31)
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "WHERE position_history.portfolio_id = 'P1'" in compiled_query
    assert "AND position_history.security_id = 'S1'" in compiled_query
    assert "AND position_history.position_date >= '2025-01-01'" in compiled_query
    assert "AND position_history.position_date <= '2025-01-31'" in compiled_query
    assert "ORDER BY position_history.position_date ASC" in compiled_query

async def test_get_latest_positions_by_portfolio(repository: PositionRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id
    WHEN get_latest_positions_by_portfolio is called
    THEN it should construct the correct complex query using a window function.
    """
    # ACT
    await repository.get_latest_positions_by_portfolio(portfolio_id="P1")

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    # Check for key components of the complex query
    assert "row_number()" in compiled_query.lower()
    assert "PARTITION BY daily_position_snapshots.security_id" in compiled_query
    assert "ORDER BY daily_position_snapshots.date DESC" in compiled_query
    assert "LEFT OUTER JOIN instruments ON instruments.security_id = ranked_snapshots.security_id" in compiled_query
    assert "WHERE ranked_snapshots.rn = 1" in compiled_query
    assert "AND ranked_snapshots.quantity > 0" in compiled_query