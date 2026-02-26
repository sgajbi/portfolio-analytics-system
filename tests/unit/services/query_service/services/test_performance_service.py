# ruff: noqa: E501
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from portfolio_common.database_models import Portfolio
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.performance_dto import PerformanceRequest
from src.services.query_service.app.services.performance_service import PerformanceService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service() -> PerformanceService:
    with (
        patch(
            "src.services.query_service.app.services.performance_service.PortfolioRepository"
        ) as portfolio_repo_cls,
        patch(
            "src.services.query_service.app.services.performance_service.PerformanceRepository"
        ) as perf_repo_cls,
    ):
        portfolio_repo = AsyncMock()
        perf_repo = AsyncMock()
        portfolio_repo.get_by_id.return_value = Portfolio(
            portfolio_id="P1", open_date=date(2020, 1, 1)
        )
        perf_repo.get_portfolio_timeseries_for_range.return_value = [
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
        portfolio_repo_cls.return_value = portfolio_repo
        perf_repo_cls.return_value = perf_repo

        svc = PerformanceService(AsyncMock(spec=AsyncSession))
        svc.portfolio_repo = portfolio_repo
        svc.repo = perf_repo
        return svc


def _request() -> PerformanceRequest:
    return PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [{"type": "YTD", "name": "YTD", "breakdown": "DAILY"}],
            "options": {
                "include_cumulative": True,
                "include_annualized": True,
                "include_attributes": True,
            },
        }
    )


async def test_calculate_performance_raises_for_missing_portfolio(
    service: PerformanceService,
) -> None:
    service.portfolio_repo.get_by_id.return_value = None
    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service.calculate_performance("P404", _request())


async def test_calculate_performance_returns_empty_when_no_timeseries(
    service: PerformanceService,
) -> None:
    service.repo.get_portfolio_timeseries_for_range.return_value = []

    result = await service.calculate_performance("P1", _request())

    assert result.summary == {}
    assert result.breakdowns is None


async def test_calculate_performance_proxies_to_lotus_performance(
    service: PerformanceService,
) -> None:
    response = SimpleNamespace()
    response.status_code = 200
    response.json = lambda: {
        "results_by_period": {
            "YTD": {
                "portfolio_return": {"base": 5.5},
                "breakdowns": {
                    "daily": [
                        {"period": "2025-01-02", "summary": {"period_return_pct": 1.0}},
                        {
                            "period": "2025-01-03",
                            "summary": {"period_return_pct": 0.5, "annualized_return_pct": 3.0},
                        },
                    ]
                },
            }
        }
    }

    with patch(
        "src.services.query_service.app.services.performance_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        result = await service.calculate_performance("P1", _request())

    assert "YTD" in result.summary
    assert result.summary["YTD"].cumulative_return == 5.5
    assert result.summary["YTD"].annualized_return == 3.0
    assert result.summary["YTD"].attributes is not None
    assert result.breakdowns is not None
    assert len(result.breakdowns["YTD"].results) == 2
    client.post.assert_awaited_once()


async def test_calculate_performance_raises_on_remote_error(service: PerformanceService) -> None:
    response = SimpleNamespace(status_code=502, text="upstream")

    with patch(
        "src.services.query_service.app.services.performance_service.httpx.AsyncClient"
    ) as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        with pytest.raises(RuntimeError, match="lotus-performance request failed"):
            await service.calculate_performance("P1", _request())

def test_period_to_pa_type_rejects_unsupported_value() -> None:
    with pytest.raises(ValueError, match="Unsupported period type"):
        PerformanceService._period_to_pa_type("BAD")


def test_breakdown_to_pa_frequencies_defaults_and_fallback() -> None:
    assert PerformanceService._breakdown_to_pa_frequencies(None) == ["monthly"]
    assert PerformanceService._breakdown_to_pa_frequencies("UNKNOWN") == ["monthly"]


def test_extract_breakdown_results_returns_empty_for_unknown_breakdown() -> None:
    results = PerformanceService._extract_breakdown_results(
        period_payload={},
        breakdown="BAD",
        default_start=date(2025, 1, 1),
        default_end=date(2025, 1, 2),
    )
    assert results == []


def test_extract_breakdown_results_handles_invalid_period_date() -> None:
    results = PerformanceService._extract_breakdown_results(
        period_payload={"breakdowns": {"daily": [{"period": "bad", "summary": {"period_return_pct": 1.2}}]}},
        breakdown="DAILY",
        default_start=date(2025, 1, 1),
        default_end=date(2025, 1, 2),
    )
    assert len(results) == 1
    assert results[0].start_date == date(2025, 1, 2)


async def test_calculate_performance_returns_empty_when_no_periods(service: PerformanceService) -> None:
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-03-31", "net_or_gross": "NET"},
            "periods": [],
            "options": {
                "include_cumulative": True,
                "include_annualized": True,
                "include_attributes": True,
            },
        }
    )
    result = await service.calculate_performance("P1", request)
    assert result.summary == {}
    assert result.breakdowns is None


async def test_calculate_performance_handles_missing_remote_period_payload(service: PerformanceService) -> None:
    response = SimpleNamespace()
    response.status_code = 200
    response.json = lambda: {"results_by_period": {}}

    with patch("src.services.query_service.app.services.performance_service.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        client_cls.return_value = client

        result = await service.calculate_performance("P1", _request())

    assert result.summary["YTD"].cumulative_return is None
