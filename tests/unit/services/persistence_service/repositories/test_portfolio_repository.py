# tests/unit/services/persistence_service/repositories/test_portfolio_repository.py
import pytest
from unittest.mock import AsyncMock, call
from datetime import date

from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.events import PortfolioEvent
from portfolio_common.database_models import Portfolio as DBPortfolio
from src.services.persistence_service.app.repositories.portfolio_repository import PortfolioRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    # Mock the execute method to be an async function
    session = AsyncMock()
    session.execute = AsyncMock()
    return session

@pytest.fixture
def repository(mock_db_session: AsyncMock) -> PortfolioRepository:
    """Provides an instance of the PortfolioRepository with a mock session."""
    return PortfolioRepository(mock_db_session)

@pytest.fixture
def sample_portfolio_event() -> PortfolioEvent:
    """Provides a sample PortfolioEvent for testing."""
    return PortfolioEvent(
        portfolioId="PORT_TEST_01",
        baseCurrency="USD",
        openDate=date(2025, 1, 1),
        cifId="CIF_TEST_1",
        status="ACTIVE",
        riskExposure="High",
        investmentTimeHorizon="Long",
        portfolioType="Discretionary",
        bookingCenter="SG"
    )

async def test_create_or_update_portfolio(repository: PortfolioRepository, mock_db_session: AsyncMock, sample_portfolio_event: PortfolioEvent):
    """
    GIVEN a portfolio event
    WHEN create_or_update_portfolio is called
    THEN it should execute a PostgreSQL upsert statement.
    """
    # Act
    result = await repository.create_or_update_portfolio(sample_portfolio_event)

    # Assert
    # 1. Check that execute was called once
    mock_db_session.execute.assert_awaited_once()
    
    # 2. Check the object returned by the method
    assert isinstance(result, DBPortfolio)
    assert result.portfolio_id == sample_portfolio_event.portfolio_id
    assert result.base_currency == sample_portfolio_event.base_currency

    # 3. Check the SQL statement that was generated and passed to execute
    executed_statement = mock_db_session.execute.call_args[0][0]
    assert isinstance(executed_statement, pg_insert)

    # Check the compiled SQL to be more specific (optional but good)
    compiled = executed_statement.compile(dialect=mock_db_session.bind.dialect)
    assert "INSERT INTO portfolios" in str(compiled)
    assert "ON CONFLICT (portfolio_id) DO UPDATE SET" in str(compiled)
    assert "base_currency = excluded.base_currency" in str(compiled)