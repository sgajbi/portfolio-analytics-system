# src/services/query_service/app/services/risk_service.py
import logging
from datetime import date

import numpy as np
import pandas as pd
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import DAILY_ROR_PCT, DATE
from performance_calculator_engine.helpers import resolve_period
from risk_analytics_engine.exceptions import InsufficientDataError
from risk_analytics_engine.helpers import convert_annual_rate_to_periodic
from risk_analytics_engine.metrics import (
    calculate_beta,
    calculate_drawdown,
    calculate_expected_shortfall,
    calculate_information_ratio,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_tracking_error,
    calculate_var,
    calculate_volatility,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.risk_dto import RiskPeriodResult, RiskRequest, RiskResponse, RiskValue
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.price_repository import MarketPriceRepository

logger = logging.getLogger(__name__)


class RiskService:
    """
    Handles the business logic for calculating portfolio risk analytics.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.perf_repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.price_repo = MarketPriceRepository(db)

    @staticmethod
    def _resample_returns(returns: pd.Series, frequency: str) -> pd.Series:
        """Resample arithmetic returns (in percentage points) to requested periodicity."""
        if returns.empty:
            return returns

        series = returns.sort_index()
        if frequency == "DAILY":
            return series

        rule = {"WEEKLY": "W-FRI", "MONTHLY": "ME"}[frequency]
        return series.resample(rule).apply(lambda x: ((1 + x / 100).prod() - 1) * 100).dropna()

    @staticmethod
    def _to_log_returns(returns: pd.Series) -> pd.Series:
        """Convert arithmetic percentage returns to log percentage returns."""
        if returns.empty:
            return returns
        return np.log1p(returns / 100) * 100

    async def _get_benchmark_returns(
        self, security_id: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetches and calculates daily returns for a benchmark security."""
        prices = await self.price_repo.get_prices(security_id, start_date, end_date)
        if len(prices) < 2:
            return pd.DataFrame()

        df = pd.DataFrame([{"date": p.price_date, "price": p.price} for p in prices])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(by="date").set_index("date")
        df["returns"] = df["price"].pct_change() * 100
        return df[["returns"]].dropna()

    async def calculate_risk(self, portfolio_id: str, request: RiskRequest) -> RiskResponse:
        logger.info("Starting risk calculation for portfolio %s", portfolio_id)
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        resolved_periods = [
            resolve_period(
                period_type=p.type,
                name=p.name or p.type,
                from_date=getattr(p, "from_date", None),
                to_date=getattr(p, "to_date", None),
                year=getattr(p, "year", None),
                inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date,
            )
            for p in request.periods
        ]
        if not resolved_periods:
            return RiskResponse(scope=request.scope, results={})

        min_start_date = min(p[1] for p in resolved_periods)
        max_end_date = max(p[2] for p in resolved_periods)

        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start_date, max_end_date
        )
        if not timeseries_data:
            return RiskResponse(scope=request.scope, results={})

        timeseries_dicts = [r.to_dict() for r in timeseries_data]
        perf_calc_config = {
            "metric_basis": request.scope.net_or_gross,
            "period_type": "EXPLICIT",
            "performance_start_date": portfolio.open_date.isoformat(),
            "report_start_date": min_start_date.isoformat(),
            "report_end_date": max_end_date.isoformat(),
        }
        calculator = PerformanceCalculator(config=perf_calc_config)
        base_returns_df = calculator.calculate_performance(timeseries_dicts)
        if base_returns_df.empty:
            return RiskResponse(scope=request.scope, results={})

        base_returns_df[DATE] = pd.to_datetime(base_returns_df[DATE])

        benchmark_returns_df = pd.DataFrame()
        benchmark_metrics = {"BETA", "TRACKING_ERROR", "INFORMATION_RATIO"}
        if request.options.benchmark_security_id and any(
            m in request.metrics for m in benchmark_metrics
        ):
            benchmark_returns_df = await self._get_benchmark_returns(
                request.options.benchmark_security_id, min_start_date, max_end_date
            )

        results = {}
        freq = request.options.frequency
        annual_factor = (
            request.options.annualization_factor
            or {"DAILY": 252, "WEEKLY": 52, "MONTHLY": 12}[freq]
        )

        periodic_rf = 0.0
        if (
            request.options.risk_free_mode == "ANNUAL_RATE"
            and request.options.risk_free_annual_rate is not None
        ):
            periodic_rf = convert_annual_rate_to_periodic(
                request.options.risk_free_annual_rate, annual_factor
            )

        periodic_mar = convert_annual_rate_to_periodic(
            request.options.mar_annual_rate, annual_factor
        )

        for name, start_date, end_date in resolved_periods:
            period_df = base_returns_df[
                (base_returns_df[DATE] >= pd.Timestamp(start_date))
                & (base_returns_df[DATE] <= pd.Timestamp(end_date))
            ]
            period_metrics = {}
            raw_returns_series = period_df.set_index(DATE)[DAILY_ROR_PCT].dropna()
            drawdown_returns_series = self._resample_returns(
                raw_returns_series, request.options.frequency
            )
            returns_series = drawdown_returns_series
            if request.options.use_log_returns:
                returns_series = self._to_log_returns(returns_series)

            if "VOLATILITY" in request.metrics:
                try:
                    period_metrics["VOLATILITY"] = RiskValue(
                        value=calculate_volatility(returns_series, annual_factor)
                    )
                except InsufficientDataError as e:
                    period_metrics["VOLATILITY"] = RiskValue(value=None, details={"error": str(e)})

            if "DRAWDOWN" in request.metrics:
                try:
                    dd_data = calculate_drawdown(returns=drawdown_returns_series)
                    period_metrics["DRAWDOWN"] = RiskValue(
                        value=dd_data["max_drawdown"], details=dd_data
                    )
                except InsufficientDataError as e:
                    period_metrics["DRAWDOWN"] = RiskValue(value=None, details={"error": str(e)})

            if "SHARPE" in request.metrics:
                try:
                    period_metrics["SHARPE"] = RiskValue(
                        value=calculate_sharpe_ratio(returns_series, periodic_rf, annual_factor)
                    )
                except InsufficientDataError as e:
                    period_metrics["SHARPE"] = RiskValue(value=None, details={"error": str(e)})

            if "SORTINO" in request.metrics:
                try:
                    period_metrics["SORTINO"] = RiskValue(
                        value=calculate_sortino_ratio(returns_series, periodic_mar, annual_factor)
                    )
                except InsufficientDataError as e:
                    period_metrics["SORTINO"] = RiskValue(value=None, details={"error": str(e)})

            if not benchmark_returns_df.empty and any(
                m in request.metrics for m in benchmark_metrics
            ):
                benchmark_period = benchmark_returns_df.loc[
                    (benchmark_returns_df.index >= pd.Timestamp(start_date))
                    & (benchmark_returns_df.index <= pd.Timestamp(end_date)),
                    "returns",
                ]
                benchmark_period = self._resample_returns(
                    benchmark_period, request.options.frequency
                )
                if request.options.use_log_returns:
                    benchmark_period = self._to_log_returns(benchmark_period)

                aligned_df = pd.merge(
                    returns_series,
                    benchmark_period.to_frame(name="returns"),
                    left_index=True,
                    right_index=True,
                    how="inner",
                )
                p_returns, b_returns = aligned_df[DAILY_ROR_PCT], aligned_df["returns"]

                if "BETA" in request.metrics:
                    try:
                        period_metrics["BETA"] = RiskValue(
                            value=calculate_beta(p_returns, b_returns)
                        )
                    except InsufficientDataError as e:
                        period_metrics["BETA"] = RiskValue(value=None, details={"error": str(e)})
                if "TRACKING_ERROR" in request.metrics:
                    try:
                        period_metrics["TRACKING_ERROR"] = RiskValue(
                            value=calculate_tracking_error(p_returns, b_returns, annual_factor)
                        )
                    except InsufficientDataError as e:
                        period_metrics["TRACKING_ERROR"] = RiskValue(
                            value=None, details={"error": str(e)}
                        )
                if "INFORMATION_RATIO" in request.metrics:
                    try:
                        period_metrics["INFORMATION_RATIO"] = RiskValue(
                            value=calculate_information_ratio(p_returns, b_returns, annual_factor)
                        )
                    except InsufficientDataError as e:
                        period_metrics["INFORMATION_RATIO"] = RiskValue(
                            value=None, details={"error": str(e)}
                        )

            if "VAR" in request.metrics:
                try:
                    var_options = request.options.var
                    var_val_base = calculate_var(
                        returns_series, var_options.confidence, var_options.method
                    )
                    var_val = var_val_base
                    if var_options.horizon_days > 1:
                        var_val = var_val * (var_options.horizon_days**0.5)

                    details = {}
                    if var_options.include_expected_shortfall:
                        es_val = calculate_expected_shortfall(
                            returns_series, var_options.confidence, var_val_base
                        )
                        if var_options.horizon_days > 1:
                            es_val = es_val * (var_options.horizon_days**0.5)
                        details["expected_shortfall"] = es_val

                    period_metrics["VAR"] = RiskValue(value=var_val, details=details or None)
                except (InsufficientDataError, ValueError) as e:
                    logger.warning("Could not calculate VaR for period '%s': %s", name, e)
                    period_metrics["VAR"] = RiskValue(value=None, details={"error": str(e)})

            results[name] = RiskPeriodResult(
                start_date=start_date, end_date=end_date, metrics=period_metrics
            )

        return RiskResponse(scope=request.scope, results=results)
