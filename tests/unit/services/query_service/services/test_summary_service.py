# tests/unit/services/query_service/services/test_summary_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.summary_service import SummaryService
from src.services.query_service.app.dtos.summary_dto import SummaryRequest
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot, Instrument, Cashflow

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the SummaryService."""
    mock_portfolio_repo = AsyncMock()
    mock_summary_repo = AsyncMock()

    mock_portfolio_repo.get_by_id.return_value = Portfolio(
        portfolio_id="P1", open_date=date(2023, 1, 1),
        base_currency="USD", risk_exposure="High", investment_time_horizon="Long",
        portfolio_type="Discretionary", booking_center="SG", cif_id="CIF_TEST", status="ACTIVE"
    )
    
    mock_snapshot_1 = DailyPositionSnapshot(security_id="S1", market_value=Decimal("50000"))
    mock_instrument_1 = Instrument(security_id="S1", product_type="Equity", asset_class="Equity", sector="Technology")
    mock_snapshot_2 = DailyPositionSnapshot(security_id="S2", market_value=Decimal("30000"))
    mock_instrument_2 = Instrument(security_id="S2", product_type="Bond", asset_class="Fixed Income", sector=None)
    mock_snapshot_3 = DailyPositionSnapshot(security_id="S3", market_value=Decimal("20000"))
    mock_instrument_3 = Instrument(security_id="S3", product_type="Cash", asset_class="Cash")
    
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (mock_snapshot_1, mock_instrument_1), (mock_snapshot_2, mock_instrument_2), (mock_snapshot_3, mock_instrument_3),
    ]
    mock_summary_repo.get_cashflows_for_period.return_value = [
        Cashflow(classification="CASHFLOW_IN", amount=Decimal("10000")),
        Cashflow(classification="CASHFLOW_OUT", amount=Decimal("-2000")),
        Cashflow(classification="TRANSFER", amount=Decimal("50000")),
        Cashflow(classification="TRANSFER", amount=Decimal("-15000")),
        Cashflow(classification="INCOME", amount=Decimal("500")),
        Cashflow(classification="EXPENSE", amount=Decimal("-100")),
    ]
    mock_summary_repo.get_realized_pnl.return_value = Decimal("1500")
    mock_summary_repo.get_total_unrealized_pnl.return_value = Decimal("0")


    with patch(
        "src.services.query_service.app.services.summary_service.PortfolioRepository",
        return_value=mock_portfolio_repo
    ), patch(
        "src.services.query_service.app.services.summary_service.SummaryRepository",
        return_value=mock_summary_repo
    ):
        service = SummaryService(AsyncMock(spec=AsyncSession))
        yield {
            "service": service,
            "summary_repo": mock_summary_repo
        }

async def test_summary_service_calculates_wealth(mock_dependencies):
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29", "period": {"type": "YTD"}, "sections": ["WEALTH"]
    })
    response = await service.get_portfolio_summary("P1", request)
    assert response.wealth is not None
    assert response.wealth.total_market_value == Decimal("100000")
    assert response.wealth.total_cash == Decimal("20000")
    assert response.allocation is None

async def test_summary_service_calculates_allocation(mock_dependencies):
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29", "period": {"type": "YTD"},
        "sections": ["ALLOCATION"], "allocation_dimensions": ["ASSET_CLASS", "SECTOR"]
    })
    response = await service.get_portfolio_summary("P1", request)
    assert response.allocation is not None
    alloc_sector = response.allocation.by_sector
    assert len(alloc_sector) == 2
    assert alloc_sector[1].group == "Unclassified"
    assert alloc_sector[1].market_value == Decimal("50000")
    assert alloc_sector[1].weight == pytest.approx(0.5)

async def test_summary_service_calculates_all_sections(mock_dependencies):
    """
    Tests that a request for all sections returns a complete, correctly calculated response
    with the new ActivitySummary structure.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    mock_summary_repo.get_total_unrealized_pnl.side_effect = [Decimal("8000"), Decimal("10500")]

    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29", "period": {"type": "YTD"},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY"]
    })

    # ACT
    response = await service.get_portfolio_summary("P1", request)

    # ASSERT
    assert response.wealth is not None
    assert response.pnl_summary is not None
    assert response.income_summary is not None
    assert response.activity_summary is not None

    # Verify Activity Summary
    activity = response.activity_summary
    assert activity.total_deposits == Decimal("10000")
    assert activity.total_withdrawals == Decimal("-2000")
    assert activity.total_transfers_in == Decimal("50000")
    assert activity.total_transfers_out == Decimal("-15000")
    assert activity.total_fees == Decimal("-100")
    
    # Verify PNL Summary (net_new_money now includes transfers)
    pnl = response.pnl_summary
    assert pnl.net_new_money == Decimal("43000") # 10k - 2k + 50k - 15k
    assert pnl.realized_pnl == Decimal("1500")
    assert pnl.unrealized_pnl_change == Decimal("2500") # 10500 end - 8000 start
    assert pnl.total_pnl == Decimal("4000")

    assert response.income_summary.total_dividends == Decimal("500")
    assert response.income_summary.total_interest == Decimal("0")