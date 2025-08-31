# tests/unit/services/query_service/services/test_position_analytics_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.position_analytics_service import PositionAnalyticsService
from src.services.query_service.app.dtos.position_analytics_dto import PositionAnalyticsRequest, PositionAnalyticsSection
from portfolio_common.database_models import DailyPositionSnapshot

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the PositionAnalyticsService."""
    mock_position_repo = AsyncMock()

    # Define the rich data tuple that the repository now returns
    mock_snapshot = DailyPositionSnapshot(
        security_id="SEC1",
        quantity=Decimal("100"),
        cost_basis=Decimal("10000"),
        market_value=Decimal("12000"),
        unrealized_gain_loss=Decimal("2000"),
        date=date(2025, 8, 30)
    )
    
    repo_return_value = [(
        mock_snapshot, "Test Instrument", "CURRENT", "ISIN123",
        "USD", "Equity", "Technology", "US"
    )]
    mock_position_repo.get_latest_positions_by_portfolio.return_value = repo_return_value

    with patch(
        "src.services.query_service.app.services.position_analytics_service.PositionRepository",
        return_value=mock_position_repo
    ):
        service = PositionAnalyticsService(AsyncMock(spec=AsyncSession))
        yield { "service": service, "position_repo": mock_position_repo }

async def test_get_position_analytics_base_sections(mock_dependencies):
    """
    GIVEN a request for BASE, INSTRUMENT_DETAILS, and VALUATION sections
    WHEN get_position_analytics is called
    THEN it should call the repository and correctly map the data to the DTO.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = PositionAnalyticsRequest(
        asOfDate=date(2025, 8, 31),
        sections=[
            PositionAnalyticsSection.BASE,
            PositionAnalyticsSection.INSTRUMENT_DETAILS,
            PositionAnalyticsSection.VALUATION
        ]
    )

    # ACT
    response = await service.get_position_analytics("P1", request)

    # ASSERT
    mock_dependencies["position_repo"].get_latest_positions_by_portfolio.assert_awaited_once_with("P1")
    
    assert response.portfolioId == "P1"
    assert response.totalMarketValue == 12000.0
    assert len(response.positions) == 1
    
    position = response.positions[0]
    assert position.securityId == "SEC1"
    assert position.quantity == 100.0
    assert position.weight == 1.0 # Only one position

    # Assert instrument details
    details = position.instrument_details
    assert details is not None
    assert details.name == "Test Instrument"
    assert details.asset_class == "Equity"
    assert details.sector == "Technology"

    # Assert valuation details
    valuation = position.valuation
    assert valuation is not None
    assert valuation.market_value.amount == 12000.0
    assert valuation.cost_basis.amount == 10000.0
    assert valuation.unrealized_pnl.amount == 2000.0

async def test_get_position_analytics_handles_no_positions(mock_dependencies):
    """
    GIVEN a portfolio with no open positions
    WHEN get_position_analytics is called
    THEN it should return an empty but valid response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_dependencies["position_repo"].get_latest_positions_by_portfolio.return_value = []
    request = PositionAnalyticsRequest(asOfDate=date(2025, 8, 31), sections=["BASE"])
    
    # ACT
    response = await service.get_position_analytics("P_EMPTY", request)

    # ASSERT
    assert response.portfolioId == "P_EMPTY"
    assert response.totalMarketValue == 0.0
    assert response.positions == []