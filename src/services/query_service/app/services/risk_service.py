# src/services/query_service/app/services/risk_service.py
import logging
import pandas as pd
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from ..dtos.risk_dto import RiskRequest, RiskResponse, RiskPeriodResult, RiskValue
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.performance_repository import PerformanceRepository
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.helpers import resolve_period
from performance_calculator_engine.constants import DATE, DAILY_ROR_PCT

# New imports for risk engine
from risk_analytics_engine.metrics import calculate_volatility, calculate_drawdown, calculate_sharpe_ratio, calculate_sortino_ratio
from risk_analytics_engine.helpers import convert_annual_rate_to_periodic
from risk_analytics_engine.exceptions import InsufficientDataError

logger = logging.getLogger(__name__)

class RiskService:
    """
    Handles the business logic for calculating portfolio risk analytics.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.perf_repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    async def calculate_risk(self, portfolio_id: str, request: RiskRequest) -> RiskResponse:
        """
        Orchestrates the fetching of data and calculation of risk metrics.
        """
        logger.info("Starting risk calculation for portfolio %s", portfolio_id)

        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            logger.warning("Portfolio %s not found.", portfolio_id)
            raise ValueError(f"Portfolio {portfolio_id} not found")

        resolved_periods = [
            resolve_period(
                period_type=p.type, name=p.name or p.type,
                from_date=getattr(p, 'from_date', None), to_date=getattr(p, 'to_date', None),
                year=getattr(p, 'year', None), inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date
            ) for p in request.periods
        ]

        if not resolved_periods:
            return RiskResponse(scope=request.scope, results={})

        min_start_date = min(p[1] for p in resolved_periods)
        max_end_date = max(p[2] for p in resolved_periods)

        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start_date, max_end_date
        )

        if not timeseries_data:
            logger.warning("No time-series data found for portfolio %s in range %s to %s.", portfolio_id, min_start_date, max_end_date)
            return RiskResponse(scope=request.scope, results={})

        timeseries_dicts = [r.to_dict() for r in timeseries_data]

        perf_calc_config = {
            "metric_basis": request.scope.net_or_gross, "period_type": "EXPLICIT",
            "performance_start_date": portfolio.open_date.isoformat(),
            "report_start_date": min_start_date.isoformat(),
            "report_end_date": max_end_date.isoformat(),
        }
        calculator = PerformanceCalculator(config=perf_calc_config)
        base_returns_df = calculator.calculate_performance(timeseries_dicts)
        
        if base_returns_df.empty:
            logger.warning("Return calculation yielded no data for portfolio %s.", portfolio_id)
            return RiskResponse(scope=request.scope, results={})

        base_returns_df[DATE] = pd.to_datetime(base_returns_df[DATE])
        
        results = {}
        default_annualization_factor = {"DAILY": 252, "WEEKLY": 52, "MONTHLY": 12}[request.options.frequency]
        annualization_factor = request.options.annualization_factor or default_annualization_factor

        periodic_rf_rate = 0.0
        if request.options.risk_free_mode == "ANNUAL_RATE" and request.options.risk_free_annual_rate is not None:
            periodic_rf_rate = convert_annual_rate_to_periodic(
                request.options.risk_free_annual_rate, annualization_factor
            )
        
        periodic_mar = convert_annual_rate_to_periodic(
            request.options.mar_annual_rate, annualization_factor
        )

        for name, start_date, end_date in resolved_periods:
            period_df = base_returns_df[
                (base_returns_df[DATE] >= pd.Timestamp(start_date)) & (base_returns_df[DATE] <= pd.Timestamp(end_date))
            ]

            period_metrics = {}
            returns_series = period_df.set_index(DATE)[DAILY_ROR_PCT]

            if "VOLATILITY" in request.metrics:
                try:
                    vol = calculate_volatility(
                        returns=returns_series, annualization_factor=annualization_factor
                    )
                    period_metrics["VOLATILITY"] = RiskValue(value=vol)
                except InsufficientDataError as e:
                    logger.warning("Could not calculate Volatility for period '%s': %s", name, e)
                    period_metrics["VOLATILITY"] = RiskValue(value=None, details={"error": str(e)})
            
            if "DRAWDOWN" in request.metrics:
                try:
                    drawdown_data = calculate_drawdown(returns=returns_series)
                    period_metrics["DRAWDOWN"] = RiskValue(
                        value=drawdown_data["max_drawdown"],
                        details={ "peak_date": drawdown_data["peak_date"], "trough_date": drawdown_data["trough_date"] }
                    )
                except InsufficientDataError as e:
                    logger.warning("Could not calculate Drawdown for period '%s': %s", name, e)
                    period_metrics["DRAWDOWN"] = RiskValue(value=None, details={"error": str(e)})

            if "SHARPE" in request.metrics:
                try:
                    sharpe = calculate_sharpe_ratio(
                        returns=returns_series,
                        periodic_risk_free_rate=periodic_rf_rate,
                        annualization_factor=annualization_factor
                    )
                    period_metrics["SHARPE"] = RiskValue(value=sharpe)
                except InsufficientDataError as e:
                    logger.warning("Could not calculate Sharpe Ratio for period '%s': %s", name, e)
                    period_metrics["SHARPE"] = RiskValue(value=None, details={"error": str(e)})
            
            if "SORTINO" in request.metrics:
                try:
                    sortino = calculate_sortino_ratio(
                        returns=returns_series,
                        periodic_mar=periodic_mar,
                        annualization_factor=annualization_factor
                    )
                    period_metrics["SORTINO"] = RiskValue(value=sortino)
                except InsufficientDataError as e:
                    logger.warning("Could not calculate Sortino Ratio for period '%s': %s", name, e)
                    period_metrics["SORTINO"] = RiskValue(value=None, details={"error": str(e)})

            results[name] = RiskPeriodResult(
                start_date=start_date, end_date=end_date, metrics=period_metrics
            )

        return RiskResponse(scope=request.scope, results=results)