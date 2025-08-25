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
    
    mock_result.all.return_value = [("mock_snapshot", "mock_name")] 
    mock_result.scalars.return_value.all.return_value = ["mock_history_1", "mock_history_2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PositionRepository:
    """Provides an instance of the repository with a mock session."""
    return PositionRepository(mock_db_session)

async def test_get_position_history_with_filters(repository: PositionRepository, mock_db_session: AsyncMock):
    """
    GIVEN various filters
    WHEN get_position_history_by_security is called
    THEN it should construct a SELECT statement with a JOIN to position_state and filter by epoch.
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
    
    assert "FROM position_history JOIN position_state" in compiled_query
    assert "position_history.epoch = position_state.epoch" in compiled_query
    assert "WHERE position_history.portfolio_id = 'P1'" in compiled_query
    assert "ORDER BY position_history.position_date ASC" in compiled_query

async def test_get_latest_positions_by_portfolio(repository: PositionRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id
    WHEN get_latest_positions_by_portfolio is called
    THEN it should construct the correct complex query joining with position_state.
    """
    # ACT
    await repository.get_latest_positions_by_portfolio(portfolio_id="P1")

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    # Check for key components of the new complex query
    assert "FROM position_state" in compiled_query
    assert "daily_position_snapshots.epoch = latest_epoch.max_epoch" in compiled_query
    assert "row_number()" in compiled_query.lower()
    assert "PARTITION BY daily_position_snapshots.security_id" in compiled_query
    assert "WHERE ranked_snapshots.rn = 1" in compiled_query