# ruff: noqa: E501
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
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
    service.perf_repo.get_portfolio_timeseries_for_range.return_value = []

    result = await service.calculate_risk("P1", _request())
    assert result.results == {}


async def test_calculate_risk_calls_lotus_performance_then_lotus_risk(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
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

    pa_response = SimpleNamespace()
    pa_response.status_code = 200
    pa_response.json = lambda: {
        "results_by_period": {
            "EXPLICIT": {
                "breakdowns": {
                    "daily": [
                        {"period": "2025-01-02", "summary": {"period_return_pct": 1.0}},
                        {"period": "2025-01-03", "summary": {"period_return_pct": 0.5}},
                    ]
                }
            }
        }
    }

    risk_response = SimpleNamespace()
    risk_response.status_code = 200
    risk_response.json = lambda: {
        "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
        "results": {
            "YTD": {
                "start_date": "2025-01-01",
                "end_date": "2025-03-31",
                "metrics": {"VOLATILITY": {"value": 0.1}},
            }
        },
    }

    with patch(
        "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = [pa_response, risk_response]
        client_cls.return_value = client

        result = await service.calculate_risk("P1", _request())

    assert "YTD" in result.results
    assert client.post.await_count == 2


async def test_calculate_risk_raises_on_risk_remote_error(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
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

    pa_response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "results_by_period": {
                "EXPLICIT": {
                    "breakdowns": {
                        "daily": [{"period": "2025-01-02", "summary": {"period_return_pct": 1.0}}]
                    }
                }
            }
        },
    )
    risk_response = SimpleNamespace(status_code=502, text="upstream")

    with patch(
        "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = [pa_response, risk_response]
        client_cls.return_value = client

        with pytest.raises(RuntimeError, match="lotus-risk request failed"):
            await service.calculate_risk("P1", _request())


async def test_build_returns_series_returns_empty_when_no_periods(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
    request = RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [],
            "metrics": ["VOLATILITY"],
        }
    )

    assert await service._build_returns_series("P1", request) == []


def test_risk_period_to_pa_type_rejects_unsupported_value() -> None:
    with pytest.raises(ValueError, match="Unsupported period type"):
        RiskService._period_to_pa_type("BAD")


async def test_build_returns_series_raises_when_portfolio_missing(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service._build_returns_series("P404", _request())


async def test_build_returns_series_handles_year_period(service: RiskService) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
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

    pa_response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "results_by_period": {
                "EXPLICIT": {
                    "breakdowns": {
                        "daily": [
                            {"period": "2025-01-02", "summary": {"period_return_pct": 1.0}},
                            {"period": None, "summary": {"period_return_pct": 1.2}},
                            {"period": "2025-01-03", "summary": {}},
                        ]
                    }
                }
            }
        },
    )

    request = RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [{"type": "YEAR", "year": 2025}],
            "metrics": ["VOLATILITY"],
        }
    )

    with patch(
        "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = pa_response
        client_cls.return_value = client

        returns = await service._build_returns_series("P1", request)

    assert returns == [{"date": "2025-01-02", "value": 1.0}]


async def test_build_returns_series_raises_on_performance_remote_error(
    service: RiskService,
) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
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
    pa_response = SimpleNamespace(status_code=502, text="upstream")

    with patch(
        "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = pa_response
        client_cls.return_value = client

        with pytest.raises(RuntimeError, match="lotus-performance request failed"):
            await service._build_returns_series("P1", _request())


async def test_build_returns_series_returns_empty_when_period_payload_missing(
    service: RiskService,
) -> None:
    service.portfolio_repo.get_by_id.return_value = SimpleNamespace(
        open_date=date(2024, 1, 1), base_currency="USD"
    )
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
    pa_response = SimpleNamespace(status_code=200, json=lambda: {"results_by_period": {}})

    with patch(
        "src.services.query_service.app.services.risk_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = pa_response
        client_cls.return_value = client

        returns = await service._build_returns_series("P1", _request())

    assert returns == []
