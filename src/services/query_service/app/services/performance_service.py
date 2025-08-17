# src/services/query_service/app/services/performance_service.py
import logging
from datetime import date
from decimal import Decimal
from typing import Dict, Tuple, List, Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from dateutil.relativedelta import relativedelta

from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import FINAL_CUMULATIVE_ROR_PCT, BOD_MARKET_VALUE, EOD_MARKET_VALUE, BOD_CASHFLOW, EOD_CASHFLOW, FEES
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.performance_dto import (
    PerformanceRequest, PerformanceResponse, PerformanceResult, PerformanceRequestPeriod,
    PerformanceAttributes, PerformanceRequestScope, PerformanceResponse, StandardPeriod,
    ExplicitPeriod, YearPeriod
)
from portfolio_common.database_models import PortfolioTimeseries

logger = logging.getLogger(__name__)


class PerformanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    def _resolve_period(
        self,
        period_request: PerformanceRequestPeriod,
        inception_date: date,
        as_of_date: date
    ) -> Tuple[str, date, date]:
        """Translates a symbolic or explicit period into a concrete start and end date."""
        name = getattr(period_request, 'name', str(getattr(period_request, 'year', period_request.type)))
        start_date, end_date = date.max, date.min

        if isinstance(period_request, StandardPeriod):
            end_date = as_of_date
            if period_request.type == "YTD":
                start_date = date(as_of_date.year, 1, 1)
            elif period_request.type == "QTD":
                quarter_month = (as_of_date.month - 1) // 3 * 3 + 1
                start_date = date(as_of_date.year, quarter_month, 1)
            elif period_request.type == "MTD":
                start_date = date(as_of_date.year, as_of_date.month, 1)
            elif period_request.type == "THREE_YEAR":
                start_date = as_of_date - relativedelta(years=3) + timedelta(days=1)
            elif period_request.type == "SI":
                start_date = inception_date
        elif isinstance(period_request, ExplicitPeriod):
            start_date, end_date = period_request.from_date, period_request.to_date
        elif isinstance(period_request, YearPeriod):
            start_date = date(period_request.year, 1, 1)
            end_date = date(period_request.year, 12, 31)

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

    def _calculate_annualized_return(self, cumulative_return: float, start_date: date, end_date: date) -> float | None:
        """Calculates annualized return if the period is over a year."""
        days = (end_date - start_date).days + 1
        if days <= 365:
            return None
        years = days / 365.25
        return ((1 + cumulative_return / 100) ** (1 / years) - 1) * 100

    def _aggregate_attributes(self, df: pd.DataFrame) -> PerformanceAttributes:
        """Aggregates financial attributes from a DataFrame for a period."""
        if df.empty:
            return PerformanceAttributes()
        
        return PerformanceAttributes(
            begin_market_value=df.iloc[0][BOD_MARKET_VALUE],
            end_market_value=df.iloc[-1][EOD_MARKET_VALUE],
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

        resolved_periods = [self._resolve_period(p, portfolio.open_date, request.scope.as_of_date) for p in request.periods]
        if not resolved_periods:
            return PerformanceResponse(portfolio_id=portfolio_id, results={})

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)

        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(
            portfolio_id=portfolio_id, start_date=min_date, end_date=max_date
        )

        if not timeseries_data:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        timeseries_df = pd.DataFrame(self._convert_timeseries_to_dict(timeseries_data))
        timeseries_df['date_col'] = pd.to_datetime(timeseries_df['date']).dt.date
        
        summary: Dict[str, PerformanceResult] = {}
        for name, start_date, end_date in resolved_periods:
            period_df = timeseries_df[(timeseries_df['date_col'] >= start_date) & (timeseries_df['date_col'] <= end_date)]
            
            if period_df.empty:
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
            results_df = calculator.calculate_performance(period_df.to_dict('records'))

            cumulative_return = 0.0
            if not results_df.empty:
                cumulative_return = results_df.iloc[-1][FINAL_CUMULATIVE_ROR_PCT]

            annualized_return = None
            if request.options.include_annualized:
                annualized_return = self._calculate_annualized_return(cumulative_return, start_date, end_date)

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
        
        # We will implement breakdowns in the next step
        return PerformanceResponse(scope=request.scope, summary=summary, breakdowns=None)