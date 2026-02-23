from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.integration_dto import PortfolioCoreSnapshotRequest
from src.services.query_service.app.services.integration_service import IntegrationService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_portfolio_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_review_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_portfolio_service: AsyncMock, mock_review_service: AsyncMock
) -> IntegrationService:
    with (
        patch(
            "src.services.query_service.app.services.integration_service.PortfolioService",
            return_value=mock_portfolio_service,
        ),
        patch(
            "src.services.query_service.app.services.integration_service.ReviewService",
            return_value=mock_review_service,
        ),
    ):
        return IntegrationService(AsyncMock(spec=AsyncSession))


async def test_get_portfolio_core_snapshot(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_review_service: AsyncMock,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center": "LON-01",
        "cif_id": "CIF-1",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-1",
        "status": "ACTIVE",
    }
    mock_review_service.get_portfolio_review.return_value = {
        "portfolio_id": "P1",
        "as_of_date": date(2026, 2, 23),
        "overview": None,
        "allocation": None,
        "performance": None,
        "riskAnalytics": None,
        "incomeAndActivity": None,
        "holdings": None,
        "transactions": None,
    }

    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "PA",
            "includeSections": ["OVERVIEW", "HOLDINGS"],
        }
    )

    response = await service.get_portfolio_core_snapshot("P1", request)

    assert response.consumer_system == "PA"
    assert response.contract_version == "v1"
    assert response.portfolio.portfolio_id == "P1"
    assert response.snapshot.portfolio_id == "P1"
