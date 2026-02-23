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


def build_request(metrics: list[str], options_override: dict | None = None) -> RiskRequest:
    options = {
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
    }
    if options_override:
        options.update(options_override)

    return RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-01-31", "net_or_gross": "NET"},
            "periods": [{"type": "YTD", "name": "YTD"}],
            "metrics": metrics,
            "options": options,
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


async def test_calculate_risk_applies_weekly_resample_and_log_returns(service: RiskService):
    base_returns_df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-13", "2025-01-14"]
            ),
            "daily_ror_pct": [1.0, 1.0, -0.5, 0.2, 0.4],
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
            return_value=0.2,
        ) as mock_vol,
    ):
        await service.calculate_risk(
            "P1",
            build_request(
                ["VOLATILITY"],
                options_override={"frequency": "WEEKLY", "use_log_returns": True},
            ),
        )

    passed_series = mock_vol.call_args.args[0]
    assert len(passed_series) == 2
    expected_weekly = RiskService._resample_returns(
        base_returns_df.set_index("date")["daily_ror_pct"], "WEEKLY"
    )
    expected_log = RiskService._to_log_returns(expected_weekly)
    assert passed_series.tolist() == pytest.approx(expected_log.tolist())


async def test_calculate_risk_scales_var_and_es_for_horizon_days(service: RiskService):
    base_returns_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
            "daily_ror_pct": [1.0, -0.5, 0.8],
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
            "src.services.query_service.app.services.risk_service.calculate_var",
            return_value=2.0,
        ) as mock_var,
        patch(
            "src.services.query_service.app.services.risk_service.calculate_expected_shortfall",
            return_value=3.0,
        ) as mock_es,
    ):
        response = await service.calculate_risk(
            "P1",
            build_request(
                ["VAR"],
                options_override={"var": {"horizon_days": 4, "include_expected_shortfall": True}},
            ),
        )

    metric = response.results["YTD"].metrics["VAR"]
    assert metric.value == pytest.approx(4.0)
    assert metric.details == {"expected_shortfall": pytest.approx(6.0)}
    assert mock_var.call_count == 1
    assert mock_es.call_count == 1


async def test_calculate_risk_returns_empty_when_resolved_periods_empty(service: RiskService):
    request = RiskRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-01-31", "net_or_gross": "NET"},
            "periods": [],
            "metrics": ["VOLATILITY"],
            "options": {"frequency": "DAILY"},
        }
    )
    response = await service.calculate_risk("P1", request)

    assert response.results == {}


async def test_calculate_risk_returns_empty_when_calculator_has_no_rows(service: RiskService):
    perf_calc = MagicMock()
    perf_calc.return_value.calculate_performance.return_value = pd.DataFrame()

    with (
        patch(
            "src.services.query_service.app.services.risk_service.resolve_period",
            return_value=("YTD", date(2025, 1, 1), date(2025, 1, 31)),
        ),
        patch(
            "src.services.query_service.app.services.risk_service.PerformanceCalculator",
            new=perf_calc,
        ),
    ):
        response = await service.calculate_risk("P1", build_request(["VOLATILITY"]))

    assert response.results == {}


async def test_get_benchmark_returns_handles_price_edge_cases(service: RiskService):
    service.price_repo.get_prices = AsyncMock(return_value=[])
    response_empty = await service._get_benchmark_returns(
        "BMK_1", date(2025, 1, 1), date(2025, 1, 31)
    )
    assert response_empty.empty

    service.price_repo.get_prices = AsyncMock(
        return_value=[
            type("P", (), {"price_date": date(2025, 1, 2), "price": 100.0})(),
            type("P", (), {"price_date": date(2025, 1, 3), "price": 102.0})(),
            type("P", (), {"price_date": date(2025, 1, 6), "price": 101.0})(),
        ]
    )
    response = await service._get_benchmark_returns("BMK_1", date(2025, 1, 1), date(2025, 1, 31))
    assert not response.empty
    assert "returns" in response.columns
    assert response.iloc[0]["returns"] == pytest.approx(2.0)


async def test_calculate_risk_zero_mode_skips_risk_free_conversion(service: RiskService):
    base_returns_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "daily_ror_pct": [0.5, 0.7],
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
            "src.services.query_service.app.services.risk_service.calculate_sharpe_ratio",
            return_value=1.1,
        ) as mock_sharpe,
        patch(
            "src.services.query_service.app.services.risk_service.convert_annual_rate_to_periodic",
            return_value=0.0,
        ) as mock_convert,
    ):
        await service.calculate_risk(
            "P1",
            build_request(
                ["SHARPE"],
                options_override={
                    "risk_free_mode": "ZERO",
                    "risk_free_annual_rate": None,
                },
            ),
        )

    assert mock_sharpe.call_args.args[1] == 0.0
    assert mock_convert.call_count == 1  # MAR only
