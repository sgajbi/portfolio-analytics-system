# src/services/query_service/app/services/performance_service.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from functools import reduce

from sqlalchemy.ext.asyncio import AsyncSession
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse, PerformanceResult

logger = logging.getLogger(__name__)

class PerformanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        
        # In a real scenario, we would implement complex logic here to determine
        # the date ranges for YTD, MTD, etc.
        # For this implementation, we will assume a simple explicit range.
        
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        # Determine the widest possible date range needed from the request
        # For simplicity, we'll find the min/max of all requested periods.
        # A real implementation would be more nuanced.
        min_date = date.max
        max_date = date.min

        for period in request.periods:
            if isinstance(period, str):
                if period == "SI":
                    min_date = min(min_date, portfolio.open_date)
                    max_date = max(max_date, date.today())
            else: # is a PerformancePeriod object
                min_date = min(min_date, period.start_date)
                max_date = max(max_date, period.end_date)

        if min_date > max_date:
            return PerformanceResponse(portfolio_id=portfolio_id, results={})

        daily_metrics = await self.repo.get_daily_metrics(
            portfolio_id=portfolio_id,
            start_date=min_date,
            end_date=max_date,
            metric_basis=request.metric_basis
        )

        # For this simplified example, we'll calculate one explicit period
        # A full implementation would loop through `request.periods`
        if not daily_metrics:
             return PerformanceResponse(portfolio_id=portfolio_id, results={})

        # Link the factors: (factor1 * factor2 * ... * factorN) - 1
        total_linking_factor = reduce(lambda x, y: x * y, [m.linking_factor for m in daily_metrics])
        final_return_pct = (total_linking_factor - Decimal(1)) * Decimal(100)

        # For this example, we'll just label the result 'TOTAL'
        # A full implementation would generate a key for each period in the request.
        return PerformanceResponse(
            portfolio_id=portfolio_id,
            results={
                "TOTAL": PerformanceResult(returnPct=float(final_return_pct))
            }
        )