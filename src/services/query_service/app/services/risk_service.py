# src/services/query_service/app/services/risk_service.py
import logging
import pandas as pd
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.risk_dto import RiskRequest, RiskResponse
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.performance_repository import PerformanceRepository
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.helpers import resolve_period

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

        # 1. Resolve all requested periods into concrete start and end dates
        resolved_periods = [
            resolve_period(
                period_type=p.type,
                name=p.name or p.type,
                from_date=getattr(p, 'from_date', None),
                to_date=getattr(p, 'to_date', None),
                year=getattr(p, 'year', None),
                inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date
            )
            for p in request.periods
        ]

        if not resolved_periods:
            return RiskResponse(scope=request.scope, results={})

        # 2. Find the single, overarching date range to fetch all data at once
        min_start_date = min(p[1] for p in resolved_periods)
        max_end_date = max(p[2] for p in resolved_periods)

        # 3. Fetch the raw time-series data for the entire range
        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start_date, max_end_date
        )

        if not timeseries_data:
            logger.warning("No time-series data found for portfolio %s in range %s to %s.", portfolio_id, min_start_date, max_end_date)
            return RiskResponse(scope=request.scope, results={})

        timeseries_dicts = [r.to_dict() for r in timeseries_data]

        # 4. Use the PerformanceCalculator to get a base DataFrame of daily returns.
        # This ensures risk metrics are based on the exact same return figures as TWR.
        perf_calc_config = {
            "metric_basis": request.scope.net_or_gross,
            "period_type": "EXPLICIT", # We manage periods manually
            "performance_start_date": portfolio.open_date.isoformat(),
            "report_start_date": min_start_date.isoformat(),
            "report_end_date": max_end_date.isoformat(),
        }
        calculator = PerformanceCalculator(config=perf_calc_config)
        base_returns_df = calculator.calculate_performance(timeseries_dicts)
        
        if base_returns_df.empty:
            logger.warning("Return calculation yielded no data for portfolio %s.", portfolio_id)
            return RiskResponse(scope=request.scope, results={})

        logger.info(
            "Successfully calculated base daily returns for %d days for portfolio %s.",
            len(base_returns_df),
            portfolio_id
        )

        # (Future steps will slice base_returns_df for each period and compute metrics)

        # Placeholder implementation
        return RiskResponse(scope=request.scope, results={})