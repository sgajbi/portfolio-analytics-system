import pytest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import DailyPositionSnapshot, Portfolio
from src.services.query_service.app.dtos.position_analytics_dto import PositionAnalyticsRequest
from src.services.query_service.app.services.position_analytics_service import (
    PositionAnalyticsService,
    get_position_analytics_service,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    mock_position_repo = AsyncMock()
    mock_portfolio_repo = AsyncMock()
    mock_cashflow_repo = AsyncMock()
    mock_fx_repo = AsyncMock()

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

    mock_position_repo.get_latest_positions_by_portfolio.return_value = [
        (
            mock_snapshot,
            "Test Instrument",
            "CURRENT",
            "ISIN123",
            "USD",
            "Equity",
            "Technology",
            "US",
            1,
        )
    ]
    mock_position_repo.get_held_since_date.return_value = date(2025, 3, 15)
    mock_cashflow_repo.get_income_cashflows_for_position.return_value = []
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
            "fx_repo": mock_fx_repo,
        }


async def test_get_position_analytics_all_sections(mock_dependencies):
    service = mock_dependencies["service"]
    request = PositionAnalyticsRequest(
        as_of_date=date(2025, 8, 31),
        sections=["BASE", "INSTRUMENT_DETAILS", "VALUATION", "INCOME"],
    )

    response = await service.get_position_analytics("P1", request)

    assert response.portfolio_id == "P1"
    assert len(response.positions) == 1
    assert response.positions[0].income is not None
    assert response.positions[0].valuation is not None
    assert response.positions[0].instrument_details is not None


async def test_get_position_analytics_handles_no_positions(mock_dependencies):
    service = mock_dependencies["service"]
    mock_dependencies["position_repo"].get_latest_positions_by_portfolio.return_value = []

    response = await service.get_position_analytics(
        "P_EMPTY", PositionAnalyticsRequest(as_of_date=date(2025, 8, 31), sections=["BASE"])
    )

    assert response.portfolio_id == "P_EMPTY"
    assert response.total_market_value == 0.0
    assert response.positions == []


async def test_get_position_analytics_portfolio_not_found(mock_dependencies):
    service = mock_dependencies["service"]
    mock_dependencies["portfolio_repo"].get_by_id.return_value = None

    with pytest.raises(ValueError, match="Portfolio P_NOT_FOUND not found"):
        await service.get_position_analytics(
            "P_NOT_FOUND", PositionAnalyticsRequest(as_of_date=date(2025, 8, 31), sections=["BASE"])
        )


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
    repo_row = (snapshot, "Instrument 2", "CURRENT", "ISIN2", "EUR", "Equity", "Tech", "DE", 2)

    request = PositionAnalyticsRequest(as_of_date=date(2025, 8, 31), sections=["BASE", "INCOME"])
    mock_dependencies["cashflow_repo"].get_income_cashflows_for_position.return_value = [
        SimpleNamespace(amount=Decimal("10"), cashflow_date=date(2025, 8, 30)),
        SimpleNamespace(amount=Decimal("5"), cashflow_date=date(2025, 8, 31)),
    ]
    mock_dependencies["fx_repo"].get_fx_rates.return_value = [
        SimpleNamespace(rate_date=date(2025, 8, 30), rate=Decimal("1.2"))
    ]

    enriched = await service._enrich_position(
        portfolio=portfolio,
        total_market_value_base=Decimal("100"),
        repo_row=repo_row,
        request=request,
    )

    assert enriched.income is not None
    assert enriched.income.local.amount == 15.0
    assert enriched.income.base.amount == pytest.approx(18.0)


async def test_get_position_analytics_service_factory():
    service = get_position_analytics_service(AsyncMock(spec=AsyncSession))
    assert isinstance(service, PositionAnalyticsService)
