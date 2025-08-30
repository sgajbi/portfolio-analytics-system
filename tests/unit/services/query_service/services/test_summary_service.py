# tests/unit/services/query_service/services/test_summary_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.summary_service import SummaryService
from src.services.query_service.app.dtos.summary_dto import SummaryRequest
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot, Instrument

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
    mock_summary_repo.get_cashflow_summary_data.return_value = {
        "CASHFLOW_IN": Decimal("10000"), "CASHFLOW_OUT": Decimal("-2000"),
        "INCOME": Decimal("500"), "EXPENSE": Decimal("-100")
    }
    mock_summary_repo.get_realized_pnl.return_value = Decimal("1500")
    # Simulate unrealized P&L increasing by 2500 during the period
    mock_summary_repo.get_total_unrealized_pnl.side_effect = [Decimal("8000"), Decimal("10500")] # Start, End

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
    """Tests that the WealthSummary is calculated correctly."""
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
    """Tests that the AllocationSummary is calculated and grouped correctly."""
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
    Tests that a request for all sections returns a complete, correctly calculated response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29", "period": {"type": "YTD"},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY"]
    })

    # ACT
    response = await service.get_portfolio_summary("P1", request)

    # ASSERT
    # Verify all sections are present
    assert response.wealth is not None
    assert response.pnl_summary is not None
    assert response.income_summary is not None
    assert response.activity_summary is not None

    # Verify PNL Summary calculations
    pnl = response.pnl_summary
    assert pnl.net_new_money == Decimal("8000") # 10000 in - 2000 out
    assert pnl.realized_pnl == Decimal("1500")
    assert pnl.unrealized_pnl_change == Decimal("2500") # 10500 end - 8000 start
    assert pnl.total_pnl == Decimal("4000") # 1500 realized + 2500 unrealized change

    # Verify Income & Activity
    assert response.income_summary.total_dividends == Decimal("500") # Uses "INCOME" for now
    assert response.activity_summary.total_inflows == Decimal("10000")
    assert response.activity_summary.total_outflows == Decimal("-2000")
    assert response.activity_summary.total_fees == Decimal("-100")
    
    # Verify correct calls to repo for PNL data
    assert mock_summary_repo.get_realized_pnl.call_count == 1
    assert mock_summary_repo.get_total_unrealized_pnl.call_count == 2