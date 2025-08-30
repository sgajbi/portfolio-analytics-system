# tests/unit/services/query_service/repositories/test_instrument_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.instrument_repository import InstrumentRepository
from portfolio_common.database_models import Instrument

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession with configurable results."""
    # This is the top-level mock for the session dependency
    session = AsyncMock(spec=AsyncSession)

    # --- New Mocking Strategy ---
    # This async function will be the side_effect for the `execute` method.
    # It creates a fresh mock result object for each call.
    async def execute_side_effect(statement):
        mock_result = MagicMock()
        if "count" in str(statement.compile()).lower():
            # If it's a count query, configure the mock to return a scalar
            mock_result.scalar.return_value = 5
        else:
            # If it's a select query, configure the chain to return a list
            mock_result.scalars.return_value.all.return_value = [Instrument(), Instrument()]
        return mock_result

    # Assign the side_effect to an AsyncMock to allow awaiting AND assertions.
    session.execute = AsyncMock(side_effect=execute_side_effect)
    
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> InstrumentRepository:
    """Provides an instance of the repository with a mock session."""
    return InstrumentRepository(mock_db_session)

async def test_get_instruments_no_filters(repository: InstrumentRepository, mock_db_session: AsyncMock):
    """
    GIVEN no filters
    WHEN get_instruments is called
    THEN it should construct a SELECT statement without a WHERE clause.
    """
    # ACT
    instruments = await repository.get_instruments(skip=0, limit=100)

    # ASSERT
    assert len(instruments) == 2
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    assert "WHERE" not in str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

async def test_get_instruments_pagination(repository: InstrumentRepository, mock_db_session: AsyncMock):
    """
    GIVEN skip and limit parameters
    WHEN get_instruments is called
    THEN the generated query should include OFFSET and LIMIT clauses.
    """
    # ACT
    await repository.get_instruments(skip=10, limit=50)

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "LIMIT 50" in compiled_query
    assert "OFFSET 10" in compiled_query

async def test_get_instruments_with_filters(repository: InstrumentRepository, mock_db_session: AsyncMock):
    """
    GIVEN security_id and product_type filters
    WHEN get_instruments is called
    THEN the generated query should include corresponding WHERE clauses.
    """
    # ACT
    await repository.get_instruments(skip=0, limit=100, security_id="SEC1", product_type="Equity")

    # ASSERT
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "WHERE instruments.security_id = 'SEC1'" in compiled_query
    assert "AND instruments.product_type = 'Equity'" in compiled_query

async def test_get_instruments_count(repository: InstrumentRepository, mock_db_session: AsyncMock):
    """
    GIVEN a call to get the count of instruments
    WHEN get_instruments_count is called
    THEN it should return the scalar value from the executed query.
    """
    # ACT
    count = await repository.get_instruments_count(product_type="Bond")

    # ASSERT
    assert count == 5
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    # Check that it's a count query with the correct filter
    assert "count(*)" in compiled_query.lower()
    assert "WHERE instruments.product_type = 'Bond'" in compiled_query