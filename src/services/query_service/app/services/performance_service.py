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
    BOD_CASHFLOW, EOD_CASHFLOW, FEES, DAILY_ROR_PCT, DATE
)
# --- End Engine Imports ---

from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.performance_dto import (
    PerformanceRequest, PerformanceResponse, PerformanceResult,
    PerformanceAttributes, PerformanceBreakdown
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
            bod_cashflow=df[BOD_CASHFLOW].sum(),
            eod_cashflow=df[EOD_CASHFLOW].sum(),
            fees=df[FEES].sum()
        )

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        resolved_periods = []
        for p in request.periods:
            period_args = { "period_type": p.type, "name": p.name or p.type, "from_date": getattr(p, 'from_date', None), "to_date": getattr(p, 'to_date', None), "year": getattr(p, 'year', None) }
            resolved_periods.append(resolve_period(inception_date=portfolio.open_date, as_of_date=request.scope.as_of_date, **period_args))
        
        if not resolved_periods:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)

        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(portfolio_id=portfolio_id, start_date=min_date, end_date=max_date)
        timeseries_dicts = self._convert_timeseries_to_dict(timeseries_data)
        
        summary: Dict[str, PerformanceResult] = {}
        breakdowns: Dict[str, PerformanceBreakdown] = {}

        for name, start_date, end_date in resolved_periods:
            period_ts_data = [ts for ts in timeseries_dicts if start_date <= date.fromisoformat(ts['date']) <= end_date]
            
            if not period_ts_data:
                summary[name] = PerformanceResult(start_date=start_date, end_date=end_date)
                continue

            config = { "metric_basis": request.scope.net_or_gross, "period_type": "EXPLICIT", "performance_start_date": portfolio.open_date.isoformat(), "report_start_date": start_date.isoformat(), "report_end_date": end_date.isoformat() }
            calculator = PerformanceCalculator(config=config)
            results_df = calculator.calculate_performance(period_ts_data)

            cumulative_return = 0.0
            if not results_df.empty:
                cumulative_return = float(results_df.iloc[-1][FINAL_CUMULATIVE_ROR_PCT])

            annualized_return = calculate_annualized_return(cumulative_return, start_date, end_date) if request.options.include_annualized else None
            attributes = self._aggregate_attributes(results_df) if request.options.include_attributes else None

            summary[name] = PerformanceResult(
                start_date=start_date, 
                end_date=end_date, 
                cumulative_return=cumulative_return if request.options.include_cumulative else None, 
                annualized_return=annualized_return, 
                attributes=attributes
            )

            requested_breakdown = next((p.breakdown for p in request.periods if (p.name or p.type) == name), None)
            if requested_breakdown and not results_df.empty:
                breakdown_results = []
                
                df_for_breakdown = results_df.copy()
                df_for_breakdown[DATE] = pd.to_datetime(df_for_breakdown[DATE])
                df_for_breakdown.set_index(DATE, inplace=True)

                resample_map = { "DAILY": "D", "WEEKLY": "W", "MONTHLY": "ME", "QUARTERLY": "QE" }
                resample_freq = resample_map.get(requested_breakdown)

                if resample_freq:
                    grouped = df_for_breakdown.resample(resample_freq)

                    for period_start_date, period_df in grouped:
                        if period_df.empty:
                            continue

                        period_start = period_df.index.min().date()
                        period_end = period_df.index.max().date()
                        
                        sub_period_ts_data = period_df.reset_index().to_dict('records')
                        
                        period_config = { "metric_basis": request.scope.net_or_gross, "period_type": "EXPLICIT", "performance_start_date": portfolio.open_date.isoformat(), "report_start_date": period_start.isoformat(), "report_end_date": period_end.isoformat() }
                        period_calculator = PerformanceCalculator(config=period_config)
                        period_results_df = period_calculator.calculate_performance(sub_period_ts_data)
                        
                        period_cumulative_return = float(period_results_df.iloc[-1][FINAL_CUMULATIVE_ROR_PCT])
                        period_annualized_return = calculate_annualized_return(period_cumulative_return, period_start, period_end)
                        period_attrs = self._aggregate_attributes(period_df) if request.options.include_attributes else None

                        result_data = {
                            "start_date": period_start, "end_date": period_end,
                            "attributes": period_attrs
                        }
                        if request.options.include_cumulative:
                            result_data["cumulative_return"] = period_cumulative_return
                        if request.options.include_annualized:
                            result_data["annualized_return"] = period_annualized_return
                        
                        result_data[f"{requested_breakdown.lower()}_return"] = period_cumulative_return
                        
                        breakdown_results.append(PerformanceResult(**result_data))
                    
                    breakdowns[name] = PerformanceBreakdown(breakdown_type=requested_breakdown, results=breakdown_results)
        
        return PerformanceResponse(scope=request.scope, summary=summary, breakdowns=breakdowns or None)