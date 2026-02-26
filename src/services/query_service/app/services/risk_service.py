from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.risk_dto import RiskPeriodResult, RiskRequest, RiskResponse, RiskValue
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from .period_resolution import resolve_request_periods


class RiskService:
    """Core-local risk placeholder service.

    lotus-core does not call lotus-performance or lotus-risk for advanced analytics.
    Risk analytics ownership is external to lotus-core.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.perf_repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    async def calculate_risk(self, portfolio_id: str, request: RiskRequest) -> RiskResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        resolved_periods = resolve_request_periods(
            request.periods,
            inception_date=portfolio.open_date,
            as_of_date=request.scope.as_of_date,
        )

        if not resolved_periods:
            return RiskResponse(scope=request.scope, results={})

        min_start = min(p[1] for p in resolved_periods)
        max_end = max(p[2] for p in resolved_periods)
        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start, max_end
        )
        if not timeseries_data:
            return RiskResponse(scope=request.scope, results={})

        results: dict[str, RiskPeriodResult] = {}
        for period_name, start_date, end_date in resolved_periods:
            results[period_name] = RiskPeriodResult(
                start_date=start_date,
                end_date=end_date,
                metrics={
                    metric: RiskValue(
                        value=None,
                        details={
                            "source": "core_data_only",
                            "reason": "advanced_risk_owned_by_lotus_risk",
                        },
                    )
                    for metric in request.metrics
                },
            )

        return RiskResponse(scope=request.scope, results=results)
