from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from portfolio_common.database_models import Portfolio, PortfolioTimeseries
from risk_analytics_engine.exceptions import InsufficientDataError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.risk_dto import RiskRequest
from src.services.query_service.app.services.risk_service import RiskService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_portfolio_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = Portfolio(portfolio_id="P1", open_date=date(2024, 1, 1))
    return repo


@pytest.fixture
def mock_performance_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_portfolio_timeseries_for_range.return_value = [
        PortfolioTimeseries(
            portfolio_id="P1",
            date=date(2025, 1, 2),
            epoch=0,
            bod_market_value=100,
            eod_market_value=101,
            bod_cashflow=0,
            eod_cashflow=0,
            fees=0,
        )
    ]
    return repo


@pytest.fixture
def service(mock_portfolio_repo: AsyncMock, mock_performance_repo: AsyncMock) -> RiskService:
    with (
        patch(
            "src.services.query_service.app.services.risk_service.PortfolioRepository",
            return_value=mock_portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceRepository",
            return_value=mock_performance_repo,
        ),
        patch("src.services.query_service.app.services.risk_service.MarketPriceRepository"),
    ):
        return RiskService(AsyncMock(spec=AsyncSession))


def build_request(metrics: list[str]) -> RiskRequest:
    return RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-01-31", "net_or_gross": "NET"},
            "periods": [{"type": "YTD", "name": "YTD"}],
            "metrics": metrics,
            "options": {
                "frequency": "DAILY",
                "risk_free_mode": "ANNUAL_RATE",
                "risk_free_annual_rate": 0.01,
                "mar_annual_rate": 0.02,
                "benchmark_security_id": "BMK_1",
                "var": {
                    "method": "HISTORICAL",
                    "confidence": 0.95,
                    "include_expected_shortfall": True,
                },
            },
        }
    )


async def test_calculate_risk_raises_for_missing_portfolio(
    service: RiskService, mock_portfolio_repo: AsyncMock
):
    mock_portfolio_repo.get_by_id.return_value = None

    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service.calculate_risk("P404", build_request(["VOLATILITY"]))


async def test_calculate_risk_returns_empty_when_no_timeseries(
    service: RiskService, mock_performance_repo: AsyncMock
):
    mock_performance_repo.get_portfolio_timeseries_for_range.return_value = []

    with patch(
        "src.services.query_service.app.services.risk_service.resolve_period",
        return_value=("YTD", date(2025, 1, 1), date(2025, 1, 31)),
    ):
        response = await service.calculate_risk("P1", build_request(["VOLATILITY"]))

    assert response.results == {}


async def test_calculate_risk_happy_path_with_benchmark_and_var(service: RiskService):
    base_returns_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
            "daily_ror_pct": [1.0, -0.5, 0.8],
        }
    )
    benchmark_returns_df = pd.DataFrame(
        {"returns": [0.8, -0.2, 0.5]},
        index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
    )

    perf_calc = MagicMock()
    perf_calc.return_value.calculate_performance.return_value = base_returns_df

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 1, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator",
            new=perf_calc,
        ),
        patch.object(
            service, "_get_benchmark_returns", AsyncMock(return_value=benchmark_returns_df)
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_volatility",
            return_value=0.11,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_drawdown",
            return_value={
                "max_drawdown": -0.07,
                "from_date": "2025-01-03",
                "to_date": "2025-01-06",
            },
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_sharpe_ratio",
            return_value=1.2,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_sortino_ratio",
            return_value=1.4,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_beta", return_value=0.9
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_tracking_error",
            return_value=0.03,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_information_ratio",
            return_value=0.6,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_var",
            return_value=-0.045,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_expected_shortfall",
            return_value=-0.062,
        ),
    ):
        response = await service.calculate_risk(
            "P1",
            build_request(
                [
                    "VOLATILITY",
                    "DRAWDOWN",
                    "SHARPE",
                    "SORTINO",
                    "BETA",
                    "TRACKING_ERROR",
                    "INFORMATION_RATIO",
                    "VAR",
                ]
            ),
        )

    assert "YTD" in response.results
    metrics = response.results["YTD"].metrics
    assert metrics["VOLATILITY"].value == 0.11
    assert metrics["DRAWDOWN"].value == -0.07
    assert metrics["SHARPE"].value == 1.2
    assert metrics["SORTINO"].value == 1.4
    assert metrics["BETA"].value == 0.9
    assert metrics["TRACKING_ERROR"].value == 0.03
    assert metrics["INFORMATION_RATIO"].value == 0.6
    assert metrics["VAR"].value == -0.045
    assert metrics["VAR"].details == {"expected_shortfall": -0.062}


async def test_calculate_risk_metric_errors_are_captured(service: RiskService):
    base_returns_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "daily_ror_pct": [1.0, 1.1],
        }
    )
    perf_calc = MagicMock()
    perf_calc.return_value.calculate_performance.return_value = base_returns_df

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 1, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator",
            new=perf_calc,
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_volatility",
            side_effect=InsufficientDataError("not enough points"),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.calculate_var",
            side_effect=ValueError("invalid var input"),
        ),
    ):
        response = await service.calculate_risk("P1", build_request(["VOLATILITY", "VAR"]))

    metrics = response.results["YTD"].metrics
    assert metrics["VOLATILITY"].value is None
    assert metrics["VOLATILITY"].details == {"error": "not enough points"}
    assert metrics["VAR"].value is None
    assert metrics["VAR"].details == {"error": "invalid var input"}
