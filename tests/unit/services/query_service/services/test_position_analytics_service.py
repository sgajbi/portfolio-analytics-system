# tests/unit/services/query_service/services/test_position_analytics_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import pandas as pd

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.position_analytics_service import (
    PositionAnalyticsService,
    get_position_analytics_service,
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


async def test_calculate_performance_returns_none_without_options(mock_dependencies):
    service = mock_dependencies["service"]
    request = PositionAnalyticsRequest(asOfDate=date(2025, 8, 31), sections=["BASE"])

    result = await service._calculate_performance(
        "P1", "SEC1", "USD", "USD", date(2023, 1, 1), request
    )

    assert result is None


async def test_calculate_performance_fx_conversion_path(mock_dependencies):
    service = mock_dependencies["service"]
    request = PositionAnalyticsRequest(
        asOfDate=date(2025, 8, 31),
        sections=["PERFORMANCE"],
        performanceOptions={"periods": ["YTD"]},
    )

    mock_dependencies["perf_repo"].get_position_timeseries_for_range.return_value = [
        SimpleNamespace(
            date=date(2025, 1, 1),
            bod_market_value=Decimal("100"),
            eod_market_value=Decimal("101"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            fees=Decimal("0"),
        ),
        SimpleNamespace(
            date=date(2025, 1, 2),
            bod_market_value=Decimal("101"),
            eod_market_value=Decimal("103"),
            bod_cashflow_position=Decimal("0"),
            eod_cashflow_position=Decimal("0"),
            fees=Decimal("0"),
        ),
    ]
    mock_dependencies["fx_repo"].get_fx_rates.return_value = [
        SimpleNamespace(rate_date=pd.Timestamp("2025-01-01"), rate=Decimal("1.3")),
        SimpleNamespace(rate_date=pd.Timestamp("2025-01-02"), rate=Decimal("1.4")),
    ]

    with patch(
        "src.services.query_service.app.services.position_analytics_service.PerformanceCalculator"
    ) as mock_calc:
        mock_calc.return_value.calculate_performance.side_effect = [
            pd.DataFrame(
                [
                    {
                        "final_cumulative_ror_pct": 2.0,
                        "date": date(2025, 1, 2),
                        "bod_market_value": Decimal("101"),
                        "eod_market_value": Decimal("103"),
                        "bod_cashflow": Decimal("0"),
                        "eod_cashflow": Decimal("0"),
                    }
                ]
            ),
            pd.DataFrame([{"final_cumulative_ror_pct": 2.7, "date": date(2025, 1, 2)}]),
        ]
        result = await service._calculate_performance(
            "P1",
            "SEC1",
            "EUR",
            "USD",
            date(2023, 1, 1),
            request,
        )

    assert result is not None
    assert "YTD" in result
    assert result["YTD"].local_return == 2.0
    assert result["YTD"].base_return == 2.7


async def test_enrich_position_income_fx_forward_fill(mock_dependencies):
    service = mock_dependencies["service"]
    portfolio = Portfolio(portfolio_id="P1", base_currency="USD", open_date=date(2023, 1, 1))
    snapshot = DailyPositionSnapshot(
        security_id="SEC2",
        quantity=Decimal("10"),
        market_value=Decimal("100"),
        market_value_local=Decimal("80"),
        cost_basis=Decimal("90"),
        cost_basis_local=Decimal("70"),
        unrealized_gain_loss=Decimal("10"),
        unrealized_gain_loss_local=Decimal("10"),
        date=date(2025, 8, 30),
    )
    repo_row = (
        snapshot,
        "Instrument 2",
        "CURRENT",
        "ISIN2",
        "EUR",
        "Equity",
        "Tech",
        "DE",
        2,
    )

    request = PositionAnalyticsRequest(
        asOfDate=date(2025, 8, 31),
        sections=["BASE", "INCOME"],
    )

    mock_dependencies["cashflow_repo"].get_income_cashflows_for_position.return_value = [
        SimpleNamespace(amount=Decimal("10"), cashflow_date=date(2025, 8, 30)),
        SimpleNamespace(amount=Decimal("5"), cashflow_date=date(2025, 8, 31)),
    ]
    mock_dependencies["fx_repo"].get_fx_rates.return_value = [
        SimpleNamespace(rate_date=date(2025, 8, 30), rate=Decimal("1.2")),
    ]

    enriched = await service._enrich_position(
        portfolio=portfolio,
        total_market_value_base=Decimal("100"),
        repo_row=repo_row,
        request=request,
    )

    assert enriched.income is not None
    assert enriched.income.local.amount == 15.0
    # 10*1.2 + 5*1.2 (forward-filled)
    assert enriched.income.base.amount == pytest.approx(18.0)


async def test_get_position_analytics_service_factory():
    service = get_position_analytics_service(AsyncMock(spec=AsyncSession))
    assert isinstance(service, PositionAnalyticsService)
