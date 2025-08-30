# tests/unit/services/query_service/services/test_summary_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
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
        portfolio_id="P1", open_date=date(2023, 1, 1)
    )
    
    # Mock data: A mix of stocks, bonds, and cash
    mock_snapshot_1 = DailyPositionSnapshot(security_id="S1", product_type="Equity", market_value=Decimal("50000"))
    mock_instrument_1 = Instrument(security_id="S1", product_type="Equity", asset_class="Equity", sector="Technology")

    mock_snapshot_2 = DailyPositionSnapshot(security_id="S2", product_type="Bond", market_value=Decimal("30000"))
    mock_instrument_2 = Instrument(security_id="S2", product_type="Bond", asset_class="Fixed Income", sector=None) # Unclassified sector

    mock_snapshot_3 = DailyPositionSnapshot(security_id="S3", product_type="Cash", market_value=Decimal("20000"))
    mock_instrument_3 = Instrument(security_id="S3", product_type="Cash", asset_class="Cash")
    
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (mock_snapshot_1, mock_instrument_1),
        (mock_snapshot_2, mock_instrument_2),
        (mock_snapshot_3, mock_instrument_3),
    ]

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
    """
    Tests that the WealthSummary is calculated correctly.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["WEALTH"]
    })

    # ACT
    response = await service.get_portfolio_summary("P1", request)

    # ASSERT
    assert response.wealth is not None
    assert response.wealth.total_market_value == Decimal("100000") # 50k + 30k + 20k
    assert response.wealth.total_cash == Decimal("20000")
    assert response.allocation is None # Not requested

async def test_summary_service_calculates_allocation(mock_dependencies):
    """
    Tests that the AllocationSummary is calculated and grouped correctly,
    including handling of "Unclassified" items.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate({
        "as_of_date": "2025-08-29",
        "period": {"type": "YTD"},
        "sections": ["ALLOCATION"],
        "allocation_dimensions": ["ASSET_CLASS", "SECTOR"]
    })

    # ACT
    response = await service.get_portfolio_summary("P1", request)
    
    # ASSERT
    assert response.wealth is None # Not requested, but calculated internally
    assert response.allocation is not None

    # Check asset class allocation
    alloc_asset_class = response.allocation.by_asset_class
    assert len(alloc_asset_class) == 3
    assert alloc_asset_class[0].group == "Cash"
    assert alloc_asset_class[0].market_value == Decimal("20000")
    assert alloc_asset_class[0].weight == pytest.approx(0.2)
    assert alloc_asset_class[1].group == "Equity"
    assert alloc_asset_class[1].market_value == Decimal("50000")
    assert alloc_asset_class[1].weight == pytest.approx(0.5)

    # Check sector allocation (includes an unclassified item)
    alloc_sector = response.allocation.by_sector
    assert len(alloc_sector) == 2
    assert alloc_sector[0].group == "Technology"
    assert alloc_sector[0].market_value == Decimal("50000")
    assert alloc_sector[0].weight == pytest.approx(0.5)
    assert alloc_sector[1].group == "Unclassified"
    assert alloc_sector[1].market_value == Decimal("30000") # The bond with no sector
    assert alloc_sector[1].weight == pytest.approx(0.3)