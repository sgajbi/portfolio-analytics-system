# tests/unit/services/query_service/repositories/test_performance_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.performance_repository import PerformanceRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["metric1", "metric2"]
    session.execute = AsyncMock(return_value=mock_result)
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PerformanceRepository:
    """Provides an instance of the repository with a mock session."""
    return PerformanceRepository(mock_db_session)

async def test_get_daily_metrics_constructs_correct_query(repository: PerformanceRepository, mock_db_session: AsyncMock):
    """
    GIVEN a set of filters
    WHEN get_daily_metrics is called
    THEN it should construct a SELECT statement with the correct WHERE and ORDER BY clauses.
    """
    # ACT
    await repository.get_daily_metrics(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        metric_basis="NET"
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "FROM daily_performance_metrics" in compiled_query
    assert "daily_performance_metrics.portfolio_id = 'P1'" in compiled_query
    assert "daily_performance_metrics.date >= '2025-01-01'" in compiled_query
    assert "daily_performance_metrics.date <= '2025-01-31'" in compiled_query
    assert "daily_performance_metrics.return_basis = 'NET'" in compiled_query
    assert "ORDER BY daily_performance_metrics.date ASC" in compiled_query

async def test_get_portfolio_timeseries_for_range_constructs_correct_query(repository: PerformanceRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio ID and date range
    WHEN get_portfolio_timeseries_for_range is called
    THEN it should construct a SELECT statement with the correct WHERE and ORDER BY clauses.
    """
    # ACT
    await repository.get_portfolio_timeseries_for_range(
        portfolio_id="P1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31)
    )

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "FROM portfolio_timeseries" in compiled_query
    assert "portfolio_timeseries.portfolio_id = 'P1'" in compiled_query
    assert "portfolio_timeseries.date >= '2025-01-01'" in compiled_query
    assert "portfolio_timeseries.date <= '2025-01-31'" in compiled_query
    assert "ORDER BY portfolio_timeseries.date ASC" in compiled_query