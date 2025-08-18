# src/services/query_service/app/services/performance_service.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional
from functools import reduce
import pandas as pd

from sqlalchemy.ext.asyncio import AsyncSession
from dateutil.relativedelta import relativedelta

# --- Import from the centralized engine ---
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.helpers import resolve_period, calculate_annualized_return
from performance_calculator_engine.constants import (
    FINAL_CUMULATIVE_ROR_PCT, BOD_MARKET_VALUE, EOD_MARKET_VALUE, 
    BOD_CASHFLOW, EOD_CASHFLOW, FEES
)
# --- End Engine Imports ---

from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.performance_dto import (
    PerformanceRequest, PerformanceResponse, PerformanceResult,
    PerformanceAttributes
)
from portfolio_common.database_models import PortfolioTimeseries

logger = logging.getLogger(__name__)


class PerformanceService:
    """
    Orchestrates performance calculation by fetching data and delegating all
    complex calculation logic to the performance-calculator-engine.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    def _convert_timeseries_to_dict(self, timeseries_data: List[PortfolioTimeseries]) -> List[Dict]:
        """Converts SQLAlchemy models to a list of dicts for the calculation engine."""
        return [
            {
                "date": r.date.isoformat(),
                "bod_market_value": r.bod_market_value,
                "eod_market_value": r.eod_market_value,
                "bod_cashflow": r.bod_cashflow,
                "eod_cashflow": r.eod_cashflow,
                "fees": r.fees,
            }
            for r in timeseries_data
        ]

    def _aggregate_attributes(self, df: pd.DataFrame) -> PerformanceAttributes:
        """Aggregates financial attributes from a DataFrame for a period."""
        if df.empty:
            return PerformanceAttributes()
        
        return PerformanceAttributes(
            begin_market_value=df.iloc[0][BOD_MARKET_VALUE],
            end_market_value=df.iloc[-1][EOD_MARKET_VALUE],
            total_cashflow=df[BOD_CASHFLOW].sum() + df[EOD_CASHFLOW].sum(),
            fees=df[FEES].sum()
        )

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        # --- FIX: Correctly unpack DTO attributes for the helper function ---
        resolved_periods = []
        for p in request.periods:
            period_args = {
                "period_type": p.type,
                "name": p.name,
                "from_date": getattr(p, 'from_date', None),
                "to_date": getattr(p, 'to_date', None),
                "year": getattr(p, 'year', None)
            }
            resolved_periods.append(
                resolve_period(
                    inception_date=portfolio.open_date,
                    as_of_date=request.scope.as_of_date,
                    **period_args
                )
            )
        # --- END FIX ---
        
        if not resolved_periods:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)

        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(
            portfolio_id=portfolio_id, start_date=min_date, end_date=max_date
        )

        timeseries_dicts = self._convert_timeseries_to_dict(timeseries_data)
        
        summary: Dict[str, PerformanceResult] = {}
        for name, start_date, end_date in resolved_periods:
            period_ts_data = [
                ts for ts in timeseries_dicts if start_date <= date.fromisoformat(ts['date']) <= end_date
            ]
            
            if not period_ts_data:
                summary[name] = PerformanceResult(start_date=start_date, end_date=end_date, cumulative_return=0.0)
                continue

            config = {
                "metric_basis": request.scope.net_or_gross,
                "period_type": "EXPLICIT",
                "performance_start_date": portfolio.open_date.isoformat(),
                "report_start_date": start_date.isoformat(),
                "report_end_date": end_date.isoformat(),
            }

            calculator = PerformanceCalculator(config=config)
            results_df = calculator.calculate_performance(period_ts_data)

            cumulative_return = 0.0
            if not results_df.empty:
                cumulative_return = float(results_df.iloc[-1][FINAL_CUMULATIVE_ROR_PCT])

            annualized_return = None
            if request.options.include_annualized:
                annualized_return = calculate_annualized_return(cumulative_return, start_date, end_date)

            attributes = None
            if request.options.include_attributes:
                attributes = self._aggregate_attributes(results_df)

            summary[name] = PerformanceResult(
                start_date=start_date,
                end_date=end_date,
                cumulative_return=cumulative_return if request.options.include_cumulative else None,
                annualized_return=annualized_return,
                attributes=attributes
            )
        
        return PerformanceResponse(scope=request.scope, summary=summary, breakdowns=None)