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
def mock_dependencies():
    """
    A fixture to patch all external dependencies for a service-level test.
    It yields the service instance and a dictionary of its mocked dependencies.
    """
    mock_portfolio_repo = AsyncMock()
    mock_portfolio_repo.get_by_id.return_value = Portfolio(
        portfolio_id="P1", open_date=date(2023, 1, 1)
    )

    mock_perf_repo = AsyncMock()
    mock_perf_repo.get_portfolio_timeseries_for_range.return_value = [
        PortfolioTimeseries(date=date(2025, 1, 1), bod_market_value=Decimal("100000")),
        PortfolioTimeseries(date=date(2025, 1, 31), eod_market_value=Decimal("115000")),
    ]

    mock_cashflow_repo = AsyncMock()
    mock_cashflow_repo.get_external_flows.return_value = [
        (date(2025, 1, 15), Decimal("5000")),
    ]

    mock_mwr_calculator = MagicMock()
    mock_mwr_calculator.compute_period_mwr.return_value = {
        "mwr": Decimal("0.0958"),
        "mwr_annualized": None,
    }

    with (
        patch(
            "src.services.query_service.app.services.mwr_service.PortfolioRepository",
            return_value=mock_portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.mwr_service.PerformanceRepository",
            return_value=mock_perf_repo,
        ),
        patch(
            "src.services.query_service.app.services.mwr_service.CashflowRepository",
            return_value=mock_cashflow_repo,
        ),
        patch(
            "src.services.query_service.app.services.mwr_service.MWRCalculator",
            return_value=mock_mwr_calculator,
        ),
    ):
        service = MWRService(AsyncMock(spec=AsyncSession))
        yield {
            "service": service,
            "portfolio_repo": mock_portfolio_repo,
            "perf_repo": mock_perf_repo,
            "cashflow_repo": mock_cashflow_repo,
            "calculator": mock_mwr_calculator,
        }


async def test_calculate_mwr_happy_path(mock_dependencies: dict):
    """
    GIVEN a valid MWR request
    WHEN calculate_mwr is called
    THEN it should orchestrate calls to repos and the calculator and return a valid response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_portfolio_repo = mock_dependencies["portfolio_repo"]
    mock_perf_repo = mock_dependencies["perf_repo"]
    mock_cashflow_repo = mock_dependencies["cashflow_repo"]
    mock_mwr_calculator = mock_dependencies["calculator"]

    request = MWRRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-01-31"},
            "periods": [{"type": "MTD", "name": "Test MTD"}],
            "options": {"annualize": True},  # Explicitly include options
        }
    )

    # ACT
    response = await service.calculate_mwr("P1", request)

    # ASSERT
    # 1. Verify Repositories and Calculator were called
    mock_portfolio_repo.get_by_id.assert_called_once_with("P1")
    mock_perf_repo.get_portfolio_timeseries_for_range.assert_awaited_once()
    mock_cashflow_repo.get_external_flows.assert_awaited_once()
    mock_mwr_calculator.compute_period_mwr.assert_called_once()

    # 2. Verify the response is correctly assembled
    assert "Test MTD" in response.summary
    result = response.summary["Test MTD"]

    assert result.mwr == pytest.approx(0.0958)
    assert result.mwr_annualized is None

    # 3. Verify attributes
    assert result.attributes.begin_market_value == Decimal("100000")
    assert result.attributes.end_market_value == Decimal("115000")
    assert result.attributes.external_contributions == Decimal("5000")
    assert result.attributes.external_withdrawals == Decimal("0")
    assert result.attributes.cashflow_count == 1

async def test_calculate_mwr_raises_when_portfolio_missing(mock_dependencies: dict):
    service = mock_dependencies["service"]
    mock_dependencies["portfolio_repo"].get_by_id.return_value = None
    request = MWRRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-01-31"},
            "periods": [{"type": "MTD", "name": "Test MTD"}],
            "options": {"annualize": False},
        }
    )
    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service.calculate_mwr("P404", request)
