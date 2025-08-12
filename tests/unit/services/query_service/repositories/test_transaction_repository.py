# tests/unit/services/query_service/repositories/test_transaction_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.transaction_repository import TransactionRepository
from portfolio_common.database_models import Transaction

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession with configurable results."""
    session = AsyncMock(spec=AsyncSession)
    
    mock_result_list = MagicMock()
    mock_result_list.scalars.return_value.all.return_value = [Transaction(), Transaction()]
    
    mock_result_scalar = MagicMock()
    mock_result_scalar.scalar.return_value = 10
    
    def execute_side_effect(statement):
        if "count" in str(statement.compile()).lower():
            return mock_result_scalar
        return mock_result_list

    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> TransactionRepository:
    """Provides an instance of the repository with a mock session."""
    return TransactionRepository(mock_db_session)

async def test_get_transactions_default_sort(repository: TransactionRepository, mock_db_session: AsyncMock):
    """
    GIVEN no specific sort order
    WHEN get_transactions is called
    THEN the query should order by transaction_date descending.
    """
    await repository.get_transactions(portfolio_id="P1", skip=0, limit=100)

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "ORDER BY transactions.transaction_date DESC" in compiled_query

async def test_get_transactions_custom_sort(repository: TransactionRepository, mock_db_session: AsyncMock):
    """
    GIVEN a custom sort field and order
    WHEN get_transactions is called
    THEN the query should use the specified order.
    """
    await repository.get_transactions(portfolio_id="P1", skip=0, limit=100, sort_by="quantity", sort_order="asc")

    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "ORDER BY transactions.quantity ASC" in compiled_query

async def test_get_transactions_invalid_sort_falls_back_to_default(repository: TransactionRepository, mock_db_session: AsyncMock):
    """
    GIVEN an invalid sort field
    WHEN get_transactions is called
    THEN the query should fall back to the default sort order.
    """
    await repository.get_transactions(portfolio_id="P1", skip=0, limit=100, sort_by="invalid_field")
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY transactions.transaction_date DESC" in compiled_query

async def test_get_transactions_with_all_filters(repository: TransactionRepository, mock_db_session: AsyncMock):
    """
    GIVEN all possible filters
    WHEN get_transactions is called
    THEN the query should contain all corresponding WHERE clauses.
    """
    await repository.get_transactions(
        portfolio_id="P1", skip=0, limit=100,
        security_id="S1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31)
    )
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.security_id = 'S1'" in compiled_query
    # FIX: Assert for the correct SQL function `date()`
    assert "date(transactions.transaction_date) >= '2025-01-01'" in compiled_query
    assert "date(transactions.transaction_date) <= '2025-01-31'" in compiled_query

async def test_get_transactions_count(repository: TransactionRepository, mock_db_session: AsyncMock):
    """
    GIVEN a set of filters
    WHEN get_transactions_count is called
    THEN it should build the correct count query and return the scalar result.
    """
    count = await repository.get_transactions_count(portfolio_id="P1", security_id="S1")

    assert count == 10
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "count(transactions.id)" in compiled_query.lower()
    assert "transactions.portfolio_id = 'P1'" in compiled_query
    assert "transactions.security_id = 'S1'" in compiled_query