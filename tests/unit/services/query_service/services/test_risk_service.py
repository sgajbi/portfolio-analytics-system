from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
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


async def test_calculate_risk_calls_lotus_risk(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = [
        SimpleNamespace(
            date=date(2025, 1, 2),
            bod_market_value=100,
            eod_market_value=101,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        ),
        SimpleNamespace(
            date=date(2025, 1, 3),
            bod_market_value=101,
            eod_market_value=102,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        ),
    ]

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 3, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator"
        ) as calc_cls,
        patch(
            "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
        ) as client_cls,
    ):
        calc = calc_cls.return_value
        calc.calculate_performance.return_value = pd.DataFrame(
            [
                {"date": pd.Timestamp("2025-01-02"), "daily_ror_pct": 1.0},
                {"date": pd.Timestamp("2025-01-03"), "daily_ror_pct": 0.5},
            ]
        )

        response = SimpleNamespace()
        response.status_code = 200
        response.json = lambda: {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "results": {
                "YTD": {
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
                    "metrics": {"VOLATILITY": {"value": 0.1}},
                }
            },
        }
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        result = await service.calculate_risk("P1", _request())

    assert "YTD" in result.results
    client.post.assert_awaited_once()


async def test_calculate_risk_raises_on_remote_error(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = [
        SimpleNamespace(
            date=date(2025, 1, 2),
            bod_market_value=100,
            eod_market_value=101,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        ),
        SimpleNamespace(
            date=date(2025, 1, 3),
            bod_market_value=101,
            eod_market_value=102,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        ),
    ]

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 3, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator"
        ) as calc_cls,
        patch(
            "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
        ) as client_cls,
    ):
        calc = calc_cls.return_value
        calc.calculate_performance.return_value = pd.DataFrame(
            [{"date": pd.Timestamp("2025-01-02"), "daily_ror_pct": 1.0}]
        )

        response = SimpleNamespace()
        response.status_code = 502
        response.text = "upstream"
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        with pytest.raises(RuntimeError, match="lotus-risk request failed"):
            await service.calculate_risk("P1", _request())


async def test_build_returns_series_returns_empty_when_no_periods(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    request = RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [],
            "metrics": ["VOLATILITY"],
        }
    )

    assert await service._build_returns_series("P1", request) == []


async def test_build_returns_series_returns_empty_when_calculator_empty(
    service: RiskService,
) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(open_date=date(2024, 1, 1))
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = [
        SimpleNamespace(
            date=date(2025, 1, 2),
            bod_market_value=100,
            eod_market_value=101,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        )
    ]

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 3, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator"
        ) as calc_cls,
    ):
        calc_cls.return_value.calculate_performance.return_value = pd.DataFrame()
        assert await service._build_returns_series("P1", _request()) == []
