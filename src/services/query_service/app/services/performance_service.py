# src/services/query_service/app/services/performance_service.py
import logging
from datetime import date, timedelta
from typing import Dict, Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from performance_calculator_engine.calculator import PerformanceCalculator
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse, PerformanceResult, PerformanceRequestPeriod
from portfolio_common.database_models import PortfolioTimeseries

logger = logging.getLogger(__name__)

class PerformanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    def _resolve_period(self, period_def: PerformanceRequestPeriod, inception_date: date) -> Tuple[str, date, date]:
        """Translates a symbolic or explicit period into a concrete start and end date."""
        name = period_def.name
        period = period_def.period
        today = date.today()

        if isinstance(period, str):
            if period == "YTD":
                start_date = date(today.year, 1, 1)
                end_date = today
            elif period == "QTD":
                quarter_month = (today.month - 1) // 3 * 3 + 1
                start_date = date(today.year, quarter_month, 1)
                end_date = today
            elif period == "MTD":
                start_date = date(today.year, today.month, 1)
                end_date = today
            elif period == "SI":
                start_date = inception_date
                end_date = today
            else:
                raise ValueError(f"Invalid symbolic period type: {period}")
        else: # Is a PerformancePeriod object
            start_date = period.start_date
            end_date = period.end_date

        # Ensure the calculation doesn't start before the portfolio existed
        start_date = max(start_date, inception_date)

        return name, start_date, end_date

    def _convert_timeseries_to_dict(self, timeseries_data: List[PortfolioTimeseries]) -> List[Dict]:
        """Converts SQLAlchemy models to a list of dicts for the calculation engine."""
        return [
            {
                "date": r.date,
                "bod_market_value": r.bod_market_value,
                "eod_market_value": r.eod_market_value,
                "bod_cashflow": r.bod_cashflow,
                "eod_cashflow": r.eod_cashflow,
                "fees": r.fees,
            }
            for r in timeseries_data
        ]

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        # 1. Resolve all requested periods to find the widest possible date range
        resolved_periods = [self._resolve_period(p, portfolio.open_date) for p in request.periods]
        if not resolved_periods:
            return PerformanceResponse(portfolio_id=portfolio_id, results={})

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)

        # 2. Fetch all necessary time-series data in a single query
        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(
            portfolio_id=portfolio_id,
            start_date=min_date,
            end_date=max_date,
        )

        if not timeseries_data:
            return PerformanceResponse(portfolio_id=portfolio_id, results={})

        timeseries_dicts = self._convert_timeseries_to_dict(timeseries_data)
        
        # 3. Loop through each requested period and calculate the result
        results: Dict[str, PerformanceResult] = {}
        for name, start_date, end_date in resolved_periods:
            
            # Filter the in-memory data for the specific period's range
            period_data = [d for d in timeseries_dicts if start_date <= d['date'] <= end_date]
            
            if not period_data:
                results[name] = PerformanceResult(returnPct=0.0)
                continue

            config = {
                "metric_basis": request.metric_basis,
                "period_type": "EXPLICIT", # The engine only needs to know the dates now
                "performance_start_date": portfolio.open_date.isoformat(),
                "report_start_date": start_date.isoformat(),
                "report_end_date": end_date.isoformat(),
            }

            calculator = PerformanceCalculator(config=config)
            results_df = calculator.calculate_performance(period_data)

            if not results_df.empty:
                final_return = results_df.iloc[-1]["final_cumulative_ror_pct"]
                results[name] = PerformanceResult(returnPct=final_return)
            else:
                results[name] = PerformanceResult(returnPct=0.0)

        return PerformanceResponse(portfolio_id=portfolio_id, results=results)