from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.query_service.app.dtos.risk_dto import RiskRequest
from src.services.query_service.app.services.risk_service import RiskService

pytestmark = pytest.mark.asyncio


def _request() -> RiskRequest:
    return RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [{"type": "YTD", "name": "YTD"}],
            "metrics": ["VOLATILITY", "SHARPE"],
        }
    )


@pytest.fixture
def service() -> RiskService:
    with (
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceRepository"
        ) as perf_repo_cls,
        patch(
            "src.services.query_service.app.services.risk_service.PortfolioRepository"
        ) as port_repo_cls,
    ):
        perf_repo = AsyncMock()
        port_repo = AsyncMock()
        perf_repo_cls.return_value = perf_repo
        port_repo_cls.return_value = port_repo
        svc = RiskService(AsyncMock())
        svc.perf_repo = perf_repo
        svc.portfolio_repo = port_repo
        return svc


async def test_calculate_risk_raises_when_portfolio_missing(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service.calculate_risk("P404", _request())


async def test_calculate_risk_returns_empty_when_no_timeseries(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = []
    result = await service.calculate_risk("P1", _request())
    assert result.results == {}


async def test_calculate_risk_returns_core_data_only_placeholder(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = [
        SimpleNamespace(date=date(2025, 1, 2), bod_market_value=100, eod_market_value=101)
    ]
    result = await service.calculate_risk("P1", _request())
    assert "YTD" in result.results
    assert (
        result.results["YTD"].metrics["VOLATILITY"].details["reason"]
        == "advanced_risk_owned_by_lotus_risk"
    )
