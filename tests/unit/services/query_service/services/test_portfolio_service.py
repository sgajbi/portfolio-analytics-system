# tests/unit/services/query_service/services/test_portfolio_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.portfolio_service import PortfolioService
from src.services.query_service.app.repositories.portfolio_repository import PortfolioRepository
from portfolio_common.database_models import Portfolio

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_portfolio_repo() -> AsyncMock:
    """Provides a mock PortfolioRepository."""
    repo = AsyncMock(spec=PortfolioRepository)
    repo.get_portfolios.return_value = [
        Portfolio(
            portfolio_id="P1",
            base_currency="USD",
            open_date=date(2025, 1, 1),
            risk_exposure="High",
            investment_time_horizon="Long",
            portfolio_type="Discretionary",
            booking_center="SG",
            cif_id="C100",
            status="ACTIVE",
            is_leverage_allowed=False
        )
    ]
    return repo

async def test_get_portfolios(mock_portfolio_repo: AsyncMock):
    """
    GIVEN filters for a portfolio query
    WHEN the portfolio service's get_portfolios method is called
    THEN it should call the repository with the correct filters
    AND correctly map the database models to the response DTO.
    """
    # ARRANGE
    # We patch the repository at the point of use within the service module
    with patch(
        "src.services.query_service.app.services.portfolio_service.PortfolioRepository",
        return_value=mock_portfolio_repo
    ) as mock_repo_class:
        
        mock_db_session = AsyncMock(spec=AsyncSession)
        service = PortfolioService(mock_db_session)
        
        filters = {
            "portfolio_id": "P1",
            "cif_id": "C100",
            "booking_center": "SG"
        }

        # ACT
        response_dto = await service.get_portfolios(**filters)

        # ASSERT
        # 1. Assert the repository was called correctly
        mock_portfolio_repo.get_portfolios.assert_awaited_once_with(**filters)

        # 2. Assert the response DTO is structured correctly
        assert len(response_dto.portfolios) == 1
        portfolio_record = response_dto.portfolios[0]
        assert portfolio_record.portfolio_id == "P1"
        assert portfolio_record.cif_id == "C100"
        assert portfolio_record.status == "ACTIVE"