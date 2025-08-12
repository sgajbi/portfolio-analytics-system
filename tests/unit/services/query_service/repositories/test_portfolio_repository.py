# tests/unit/services/query_service/repositories/test_portfolio_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.repositories.portfolio_repository import PortfolioRepository
from portfolio_common.database_models import Portfolio

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    
    # Mock the chain of calls to return a sample list of portfolios
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        Portfolio(portfolio_id="P1"), Portfolio(portfolio_id="P2")
    ]
    session.execute.return_value = mock_result
    
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PortfolioRepository:
    """Provides an instance of the repository with a mock session."""
    return PortfolioRepository(mock_db_session)

async def test_get_portfolios_no_filters(repository: PortfolioRepository, mock_db_session: AsyncMock):
    """
    GIVEN no filters
    WHEN get_portfolios is called
    THEN it should construct a simple SELECT statement without any WHERE clauses.
    """
    # ACT
    portfolios = await repository.get_portfolios()

    # ASSERT
    assert len(portfolios) == 2
    mock_db_session.execute.assert_awaited_once()
    
    executed_stmt = mock_db_session.execute.call_args[0][0]
    # Check that the compiled query doesn't contain a WHERE clause
    assert "WHERE" not in str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "portfolios" in str(executed_stmt.compile())

async def test_get_portfolios_with_portfolio_id_filter(repository: PortfolioRepository, mock_db_session: AsyncMock):
    """
    GIVEN a portfolio_id filter
    WHEN get_portfolios is called
    THEN it should construct a SELECT statement with a WHERE clause for portfolio_id.
    """
    # ACT
    await repository.get_portfolios(portfolio_id="P1")

    # ASSERT
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    
    assert "WHERE portfolios.portfolio_id = 'P1'" in compiled_query

async def test_get_portfolios_with_all_filters(repository: PortfolioRepository, mock_db_session: AsyncMock):
    """
    GIVEN all possible filters
    WHEN get_portfolios is called
    THEN it should construct a SELECT statement with all corresponding WHERE clauses.
    """
    # ACT
    await repository.get_portfolios(
        portfolio_id="P1",
        cif_id="C100",
        booking_center="SG"
    )

    # ASSERT
    mock_db_session.execute.assert_awaited_once()
    executed_stmt = mock_db_session.execute.call_args[0][0]
    compiled_query = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "portfolios.portfolio_id = 'P1'" in compiled_query
    assert "portfolios.cif_id = 'C100'" in compiled_query
    assert "portfolios.booking_center = 'SG'" in compiled_query