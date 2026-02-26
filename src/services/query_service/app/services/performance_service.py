from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.performance_dto import (
    PerformanceAttributes,
    PerformanceBreakdown,
    PerformanceRequest,
    PerformanceResponse,
    PerformanceResult,
)
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from .period_resolution import resolve_request_periods


class PerformanceService:
    """Core-local performance summary service.

    This service intentionally avoids outbound calls to lotus-performance.
    lotus-core remains core-data only; advanced analytics are served by lotus-performance.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    @staticmethod
    def _aggregate_attributes_from_timeseries(timeseries_slice: list[Any]) -> PerformanceAttributes:
        if not timeseries_slice:
            return PerformanceAttributes()
        return PerformanceAttributes(
            begin_market_value=timeseries_slice[0].bod_market_value,
            end_market_value=timeseries_slice[-1].eod_market_value,
            total_cashflow=sum(
                (r.bod_cashflow or Decimal(0)) + (r.eod_cashflow or Decimal(0))
                for r in timeseries_slice
            ),
            bod_cashflow=sum((r.bod_cashflow or Decimal(0)) for r in timeseries_slice),
            eod_cashflow=sum((r.eod_cashflow or Decimal(0)) for r in timeseries_slice),
            fees=sum((r.fees or Decimal(0)) for r in timeseries_slice),
        )

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        resolved_periods = resolve_request_periods(
            request.periods,
            inception_date=portfolio.open_date,
            as_of_date=request.scope.as_of_date,
        )

        if not resolved_periods:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)
        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_date, max_date
        )
        if not timeseries_data:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        summary: dict[str, PerformanceResult] = {}
        breakdowns: dict[str, PerformanceBreakdown] = {}

        for period_name, start_date, end_date in resolved_periods:
            period_slice = [row for row in timeseries_data if start_date <= row.date <= end_date]
            summary[period_name] = PerformanceResult(
                start_date=start_date,
                end_date=end_date,
                cumulative_return=None,
                annualized_return=None,
                attributes=(
                    self._aggregate_attributes_from_timeseries(period_slice)
                    if request.options.include_attributes
                    else None
                ),
            )

        return PerformanceResponse(
            scope=request.scope, summary=summary, breakdowns=breakdowns or None
        )
