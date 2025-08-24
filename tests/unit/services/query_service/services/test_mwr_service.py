# tests/unit/services/query_service/services/test_mwr_service.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.mwr_service import MWRService
from src.services.query_service.app.dtos.mwr_dto import MWRRequest
from portfolio_common.database_models import Portfolio, PortfolioTimeseries

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_portfolio_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = Portfolio(portfolio_id="P1", open_date=date(2023, 1, 1))
    return repo

@pytest.fixture
def mock_perf_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_portfolio_timeseries_for_range.return_value = [
        PortfolioTimeseries(date=date(2025, 1, 1), bod_market_value=Decimal("100000")),
        PortfolioTimeseries(date=date(2025, 1, 31), eod_market_value=Decimal("115000")),
    ]
    return repo

@pytest.fixture
def mock_cashflow_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_external_flows.return_value = [
        (date(2025, 1, 15), Decimal("5000")),
    ]
    return repo

@pytest.fixture
def mock_mwr_calculator() -> MagicMock:
    mock_calc = MagicMock()
    mock_calc.compute_period_mwr.return_value = {
        "mwr": Decimal("0.0958"),
        "mwr_annualized": None,
    }
    return mock_calc

@pytest.fixture
def service(
    mock_portfolio_repo: AsyncMock,
    mock_perf_repo: AsyncMock,
    mock_cashflow_repo: AsyncMock
) -> MWRService:
    """Provides an MWRService instance with mocked repositories."""
    with patch(
        "src.services.query_service.app.services.mwr_service.PortfolioRepository",
        return_value=mock_portfolio_repo
    ), patch(
        "src.services.query_service.app.services.mwr_service.PerformanceRepository",
        return_value=mock_perf_repo
    ), patch(
        "src.services.query_service.app.services.mwr_service.CashflowRepository",
        return_value=mock_cashflow_repo
    ):
        return MWRService(AsyncMock(spec=AsyncSession))

async def test_calculate_mwr_happy_path(
    service: MWRService,
    mock_portfolio_repo: AsyncMock,
    mock_perf_repo: AsyncMock,
    mock_cashflow_repo: AsyncMock,
    mock_mwr_calculator: MagicMock
):
    """
    GIVEN a valid MWR request
    WHEN calculate_mwr is called
    THEN it should orchestrate calls to repos and the calculator and return a valid response.
    """
    # ARRANGE
    request = MWRRequest.model_validate({
        "scope": {"as_of_date": "2025-01-31"},
        "periods": [{"type": "MTD", "name": "Test MTD"}],
    })

    with patch(
        "src.services.query_service.app.services.mwr_service.MWRCalculator",
        return_value=mock_mwr_calculator
    ):
        # ACT
        response = await service.calculate_mwr("P1", request)

        # ASSERT
        mock_portfolio_repo.get_by_id.assert_called_once_with("P1")
        mock_perf_repo.get_portfolio_timeseries_for_range.assert_awaited_once()
        mock_cashflow_repo.get_external_flows.assert_awaited_once()
        mock_mwr_calculator.compute_period_mwr.assert_called_once()
        
        # Verify response structure
        assert "Test MTD" in response.summary
        result = response.summary["Test MTD"]
        
        assert result.mwr == pytest.approx(0.0958)
        assert result.mwr_annualized is None
        
        # Verify attributes
        assert result.attributes.begin_market_value == Decimal("100000")
        assert result.attributes.end_market_value == Decimal("115000")
        assert result.attributes.external_contributions == Decimal("5000")
        assert result.attributes.external_withdrawals == Decimal("0")
        assert result.attributes.cashflow_count == 1