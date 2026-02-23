# tests/unit/services/query_service/services/test_position_analytics_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.position_analytics_service import (
    PositionAnalyticsService,
)
from src.services.query_service.app.dtos.position_analytics_dto import (
    PositionAnalyticsRequest,
    PositionAnalyticsSection,
)
from portfolio_common.database_models import DailyPositionSnapshot, Portfolio

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the PositionAnalyticsService."""
    mock_position_repo = AsyncMock()
    mock_portfolio_repo = AsyncMock()
    mock_cashflow_repo = AsyncMock()
    mock_perf_repo = AsyncMock()
    mock_fx_repo = AsyncMock()  # Add mock for FxRateRepository

    # Configure mock return values
    mock_portfolio_repo.get_by_id.return_value = Portfolio(
        portfolio_id="P1", base_currency="USD", open_date=date(2023, 1, 1)
    )

    mock_snapshot = DailyPositionSnapshot(
        security_id="SEC1",
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        market_value=Decimal("12000"),
        unrealized_gain_loss=Decimal("2000"),
        date=date(2025, 8, 30),
    )

    repo_return_value = [
        (
            mock_snapshot,
            "Test Instrument",
            "CURRENT",
            "ISIN123",
            "USD",
            "Equity",
            "Technology",
            "US",
            1,  # epoch
        )
    ]
    mock_position_repo.get_latest_positions_by_portfolio.return_value = repo_return_value
    mock_position_repo.get_held_since_date.return_value = date(2025, 3, 15)

    # FIX: This method no longer exists, but the new one returns a list of cashflows
    mock_cashflow_repo.get_income_cashflows_for_position.return_value = []

    mock_perf_repo.get_position_timeseries_for_range.return_value = []

    # FIX: Add mock for fx_repo
    mock_fx_repo.get_fx_rates.return_value = []

    with (
        patch(
            "src.services.query_service.app.services.position_analytics_service.PositionRepository",
            return_value=mock_position_repo,
        ),
        patch(
            "src.services.query_service.app.services.position_analytics_service.PortfolioRepository",
            return_value=mock_portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.position_analytics_service.CashflowRepository",
            return_value=mock_cashflow_repo,
        ),
        patch(
            "src.services.query_service.app.services.position_analytics_service.PerformanceRepository",
            return_value=mock_perf_repo,
        ),
        patch(  # Add patch for the new FxRateRepository dependency
            "src.services.query_service.app.services.position_analytics_service.FxRateRepository",
            return_value=mock_fx_repo,
        ),
    ):
        service = PositionAnalyticsService(AsyncMock(spec=AsyncSession))
        yield {
            "service": service,
            "position_repo": mock_position_repo,
            "portfolio_repo": mock_portfolio_repo,
            "cashflow_repo": mock_cashflow_repo,
            "perf_repo": mock_perf_repo,
            "fx_repo": mock_fx_repo,
        }


async def test_get_position_analytics_all_sections(mock_dependencies):
    """
    GIVEN a request for all sections
    WHEN get_position_analytics is called
    THEN it should call all necessary repositories and map the data to the DTO.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = PositionAnalyticsRequest(
        asOfDate=date(2025, 8, 31),
        sections=[
            PositionAnalyticsSection.BASE,
            PositionAnalyticsSection.INSTRUMENT_DETAILS,
            PositionAnalyticsSection.VALUATION,
            PositionAnalyticsSection.INCOME,
            PositionAnalyticsSection.PERFORMANCE,
        ],
        performanceOptions={"periods": ["YTD"]},
    )

    # ACT
    response = await service.get_position_analytics("P1", request)

    # ASSERT
    mock_dependencies["position_repo"].get_latest_positions_by_portfolio.assert_awaited_once_with(
        "P1"
    )
    mock_dependencies["position_repo"].get_held_since_date.assert_awaited_once_with("P1", "SEC1", 1)

    # --- FIX: Assert the correct repository method is called ---
    mock_dependencies["cashflow_repo"].get_income_cashflows_for_position.assert_awaited_once()

    mock_dependencies["perf_repo"].get_position_timeseries_for_range.assert_awaited_once()

    assert response.portfolio_id == "P1"
    assert len(response.positions) == 1

    position = response.positions[0]

    assert position.held_since_date == date(2025, 3, 15)
    assert position.income is not None
    assert position.income.local.amount == 0.0  # Mock returns empty list
    assert position.performance is not None
    assert "YTD" in position.performance


async def test_get_position_analytics_handles_no_positions(mock_dependencies):
    """
    GIVEN a portfolio with no open positions
    WHEN get_position_analytics is called
    THEN it should return a valid, empty response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_dependencies["position_repo"].get_latest_positions_by_portfolio.return_value = []
    request = PositionAnalyticsRequest(asOfDate=date(2025, 8, 31), sections=["BASE"])

    # ACT
    response = await service.get_position_analytics("P_EMPTY", request)

    # ASSERT
    assert response.portfolio_id == "P_EMPTY"
    assert response.total_market_value == 0.0
    assert response.positions == []


async def test_get_position_analytics_portfolio_not_found(mock_dependencies):
    """
    GIVEN a request for a portfolio that does not exist
    WHEN get_position_analytics is called
    THEN it should raise a ValueError.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_dependencies["portfolio_repo"].get_by_id.return_value = None
    request = PositionAnalyticsRequest(asOfDate=date(2025, 8, 31), sections=["BASE"])

    # ACT & ASSERT
    with pytest.raises(ValueError, match="Portfolio P_NOT_FOUND not found"):
        await service.get_position_analytics("P_NOT_FOUND", request)
