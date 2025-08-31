# tests/unit/services/query_service/services/test_concentration_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.concentration_service import ConcentrationService
from src.services.query_service.app.dtos.concentration_dto import ConcentrationRequest
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the ConcentrationService."""
    mock_portfolio_repo = AsyncMock()
    mock_position_repo = AsyncMock()

    mock_portfolio_repo.get_by_id.return_value = Portfolio(
        portfolio_id="P1", open_date=date(2023, 1, 1)
    )

    # Mock the return value of get_latest_positions_by_portfolio
    # It returns a list of tuples: (DailyPositionSnapshot, instrument_name, status, asset_class)
    mock_snapshot_1 = DailyPositionSnapshot(security_id="S1", market_value=Decimal("60000"))
    mock_snapshot_2 = DailyPositionSnapshot(security_id="S2", market_value=Decimal("40000"))
    mock_position_repo.get_latest_positions_by_portfolio.return_value = [
        (mock_snapshot_1, "Stock A", "CURRENT", "Equity"),
        (mock_snapshot_2, "Stock B", "CURRENT", "Equity"),
    ]

    with patch(
        "src.services.query_service.app.services.concentration_service.PortfolioRepository",
        return_value=mock_portfolio_repo
    ), patch(
        "src.services.query_service.app.services.concentration_service.PositionRepository",
        return_value=mock_position_repo
    ):
        service = ConcentrationService(AsyncMock(spec=AsyncSession))
        yield { "service": service, "position_repo": mock_position_repo }


async def test_calculate_concentration_happy_path(mock_dependencies):
    """
    GIVEN a valid request for BULK concentration
    WHEN the service is called with a portfolio that has positions
    THEN it should return a response with correctly calculated bulk metrics.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = ConcentrationRequest.model_validate({
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"],
        "options": {"bulk_top_n": [1]}
    })

    # ACT
    response = await service.calculate_concentration("P1", request)

    # ASSERT
    assert response.scope.as_of_date == date(2025, 8, 31)
    assert response.summary.portfolio_market_value == pytest.approx(100000.0)
    
    bulk = response.bulk_concentration
    assert bulk is not None
    
    # single_position_weight = 60000 / 100000 = 0.6
    assert bulk.single_position_weight == pytest.approx(0.6)
    # HHI = (0.6^2 + 0.4^2) = 0.36 + 0.16 = 0.52
    assert bulk.hhi == pytest.approx(0.52)
    # Top 1 = 60%
    assert bulk.top_n_weights["1"] == pytest.approx(0.6)


async def test_calculate_concentration_for_empty_portfolio(mock_dependencies):
    """
    GIVEN a valid request
    WHEN the portfolio has no positions
    THEN it should return a valid, zeroed-out response.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_position_repo = mock_dependencies["position_repo"]
    mock_position_repo.get_latest_positions_by_portfolio.return_value = [] # No positions

    request = ConcentrationRequest.model_validate({
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    })

    # ACT
    response = await service.calculate_concentration("P1", request)

    # ASSERT
    assert response.summary.portfolio_market_value == 0.0
    assert response.summary.findings == []
    assert response.bulk_concentration.single_position_weight == 0.0
    assert response.bulk_concentration.hhi == 0.0