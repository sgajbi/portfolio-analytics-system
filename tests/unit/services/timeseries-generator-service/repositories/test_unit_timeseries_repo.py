# tests/unit/services/timeseries-generator-service/repositories/test_unit_timeseries_repo.py
import pytest
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text, TextClause
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql
from unittest.mock import AsyncMock, MagicMock

from portfolio_common.database_models import PortfolioAggregationJob, PositionTimeseries, PortfolioTimeseries
from src.services.timeseries_generator_service.app.repositories.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a versatile mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    
    mock_result.scalars.return_value.all.return_value = ["item1", "item2"]
    mock_result.scalars.return_value.first.return_value = "item1"
    mock_result.mappings.return_value.all.return_value = [
        {"id": 1, "portfolio_id": "P1", "aggregation_date": date(2025, 1, 1)}
    ]
    mock_result.scalar.return_value = True
    mock_result.fetchall.return_value = [MagicMock(security_id="SEC1")]
    mock_result.rowcount = 1

    session.execute = AsyncMock(return_value=mock_result)
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TimeseriesRepository:
    """Provides an instance of the repository with a mock session."""
    return TimeseriesRepository(mock_db_session)

async def test_find_and_claim_eligible_jobs(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the raw SQL query for claiming jobs."""
    await repository.find_and_claim_eligible_jobs(batch_size=50)
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    assert isinstance(executed_stmt, TextClause)
    assert "UPDATE portfolio_aggregation_jobs" in str(executed_stmt)
    assert "FOR UPDATE SKIP LOCKED" in str(executed_stmt)
    params = mock_db_session.execute.call_args[0][1]
    assert params['batch_size'] == 50

async def test_get_simple_getters(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Tests all simple getter methods that filter by a single ID."""
    await repository.get_portfolio("P1")
    compiled_query = str(mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE portfolios.portfolio_id = 'P1'" in compiled_query

    await repository.get_instrument("S1")
    compiled_query = str(mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE instruments.security_id = 'S1'" in compiled_query

async def test_get_fx_rate(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the query for the latest FX rate."""
    await repository.get_fx_rate("USD", "EUR", date(2025, 1, 10))
    compiled_query = str(mock_db_session.execute.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE fx_rates.from_currency = 'USD' AND fx_rates.to_currency = 'EUR' AND fx_rates.rate_date <= '2025-01-10'" in compiled_query
    assert "ORDER BY fx_rates.rate_date DESC" in compiled_query

async def test_is_first_position(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the query that checks for prior transaction history."""
    result = await repository.is_first_position("P1", "S1", date(2025, 1, 10))
    assert result is False
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "date(transactions.transaction_date) < '2025-01-10'" in compiled_query

async def test_upsert_position_timeseries(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the construction of the position timeseries upsert statement."""
    record = PositionTimeseries(portfolio_id="P1", security_id="S1", date=date(2025, 1, 10))
    await repository.upsert_position_timeseries(record)
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_stmt = str(executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "INSERT INTO position_timeseries" in compiled_stmt
    assert "ON CONFLICT (portfolio_id, security_id, date) DO UPDATE" in compiled_stmt

async def test_upsert_portfolio_timeseries(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the construction of the portfolio timeseries upsert statement."""
    record = PortfolioTimeseries(portfolio_id="P1", date=date(2025, 1, 10))
    await repository.upsert_portfolio_timeseries(record)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_stmt = str(executed_stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "INSERT INTO portfolio_timeseries" in compiled_stmt
    assert "ON CONFLICT (portfolio_id, date) DO UPDATE" in compiled_stmt

async def test_get_all_open_positions_as_of(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the raw SQL query for finding all open positions."""
    await repository.get_all_open_positions_as_of("P1", date(2025, 1, 10))
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    params = mock_db_session.execute.call_args[0][1]
    
    assert "SELECT DISTINCT security_id" in str(executed_stmt)
    assert "FROM position_timeseries" in str(executed_stmt)
    assert params['portfolio_id'] == 'P1'

async def test_find_and_reset_stale_jobs(repository: TimeseriesRepository, mock_db_session: AsyncMock):
    """Verifies the UPDATE statement for resetting stale jobs."""
    await repository.find_and_reset_stale_jobs()
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "UPDATE portfolio_aggregation_jobs" in compiled_query
    assert "SET status='PENDING'" in compiled_query
    assert "WHERE portfolio_aggregation_jobs.status = 'PROCESSING'" in compiled_query