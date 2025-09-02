# tests/unit/services/query_service/services/test_concentration_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.concentration_service import ConcentrationService
from src.services.query_service.app.dtos.concentration_dto import ConcentrationRequest
from portfolio_common.database_models import Portfolio, DailyPositionSnapshot
from portfolio_common.monitoring import (
    CONCENTRATION_CALCULATION_DURATION_SECONDS,
    CONCENTRATION_LOOKTHROUGH_REQUESTS_TOTAL
)

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
    # It returns a list of 6-item tuples
    mock_snapshot_1 = DailyPositionSnapshot(security_id="S1_JPM", market_value=Decimal("60000"))
    mock_snapshot_2 = DailyPositionSnapshot(security_id="S2_MSFT", market_value=Decimal("40000"))
    mock_position_repo.get_latest_positions_by_portfolio.return_value = [
        (mock_snapshot_1, "JPM Bond", "CURRENT", "Fixed Income", "JPM_ISSUER", "JPM_PARENT"),
        (mock_snapshot_2, "Microsoft Stock", "CURRENT", "Equity", "MSFT_ISSUER", "MSFT_PARENT"),
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


async def test_calculate_bulk_concentration(mock_dependencies):
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


async def test_calculate_issuer_concentration(mock_dependencies):
    """
    GIVEN a valid request for ISSUER concentration
    WHEN the service is called
    THEN it should return a response with correctly calculated issuer metrics.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = ConcentrationRequest.model_validate({
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["ISSUER"],
        "options": {"issuer_top_n": 5}
    })

    # ACT
    response = await service.calculate_concentration("P1", request)

    # ASSERT
    assert response.issuer_concentration is not None
    top_exposures = response.issuer_concentration.top_exposures
    assert len(top_exposures) == 2

    jpm_exposure = next(item for item in top_exposures if item.issuer_name == "JPM Bond")
    msft_exposure = next(item for item in top_exposures if item.issuer_name == "Microsoft Stock")

    assert jpm_exposure.exposure == pytest.approx(60000.0)
    assert jpm_exposure.weight == pytest.approx(0.6)
    assert msft_exposure.exposure == pytest.approx(40000.0)
    assert msft_exposure.weight == pytest.approx(0.4)


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
        "metrics": ["BULK", "ISSUER"]
    })

    # ACT
    response = await service.calculate_concentration("P1", request)

    # ASSERT
    assert response.summary.portfolio_market_value == 0.0
    assert response.summary.findings == []
    assert response.bulk_concentration.single_position_weight == 0.0
    assert response.issuer_concentration.top_exposures == []

@patch('src.services.query_service.app.services.concentration_service.CONCENTRATION_CALCULATION_DURATION_SECONDS')
async def test_calculate_concentration_records_metric(mock_metric_histogram, mock_dependencies):
    """
    GIVEN a valid request
    WHEN calculate_concentration is called
    THEN it should observe the duration in the Prometheus histogram.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = ConcentrationRequest.model_validate({
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": ["BULK"]
    })
    
    # ACT
    await service.calculate_concentration("P1", request)

    # ASSERT
    mock_metric_histogram.labels.assert_called_once_with(portfolio_id="P1")
    mock_metric_histogram.labels.return_value.time.return_value.__enter__.assert_called_once()
    mock_metric_histogram.labels.return_value.time.return_value.__exit__.assert_called_once()

@patch('src.services.query_service.app.services.concentration_service.CONCENTRATION_LOOKTHROUGH_REQUESTS_TOTAL')
@pytest.mark.parametrize("lookthrough_enabled, metrics, expected_calls", [
    (True, ["ISSUER", "BULK"], 1), # Lookthrough enabled, issuer requested -> should be called
    (False, ["ISSUER", "BULK"], 0), # Lookthrough disabled -> should not be called
    (True, ["BULK"], 0), # Issuer not requested -> should not be called
])
async def test_calculate_concentration_records_lookthrough_metric(
    mock_metric_counter, lookthrough_enabled, metrics, expected_calls, mock_dependencies
):
    """
    GIVEN a request with different lookthrough options
    WHEN calculate_concentration is called
    THEN it should increment the lookthrough counter only when appropriate.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    request = ConcentrationRequest.model_validate({
        "scope": {"as_of_date": "2025-08-31"},
        "metrics": metrics,
        "options": {"lookthrough_enabled": lookthrough_enabled}
    })

    # ACT
    await service.calculate_concentration("P1", request)

    # ASSERT
    if expected_calls > 0:
        mock_metric_counter.labels.assert_called_once_with(portfolio_id="P1")
        mock_metric_counter.labels.return_value.inc.assert_called_once()
    else:
        mock_metric_counter.labels.assert_not_called()