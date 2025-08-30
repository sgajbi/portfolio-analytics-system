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

    # --- Mocks for the `select` query path ---
    # This is the final list we want returned
    mock_instrument_list = [Instrument(), Instrument()]
    # This is the mock for the object returned by `.scalars()`
    mock_scalars_obj = MagicMock()
    mock_scalars_obj.all.return_value = mock_instrument_list
    # This is the mock for the object returned by `execute()`
    mock_list_result = MagicMock()
    mock_list_result.scalars.return_value = mock_scalars_obj

    # --- Mocks for the `count` query path ---
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 5

    # This async function will be the side_effect for the `execute` method
    async def execute_side_effect(statement):
        # `statement` is the actual SQLAlchemy statement object
        if "count" in str(statement.compile()).lower():
            return mock_count_result
        return mock_list_result

    # CRITICAL: Assign the side_effect to an AsyncMock to allow awaiting AND assertions
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