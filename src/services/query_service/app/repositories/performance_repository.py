# src/services/query_service/app/repositories/performance_repository.py
import logging
from typing import List
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import PortfolioTimeseries, PositionState
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class PerformanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PerformanceRepository", method="get_portfolio_timeseries_for_range")
    async def get_portfolio_timeseries_for_range(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
    ) -> List[PortfolioTimeseries]:
        """
        Fetches the raw, daily portfolio_timeseries data required for performance
        calculations, ensuring it only selects data from the portfolio's current epoch.
        """
        # Subquery to find the maximum (current) epoch for the given portfolio.
        # This is determined by the max epoch of any security within that portfolio.
        current_epoch_subq = (
            select(func.max(PositionState.epoch))
            .where(PositionState.portfolio_id == portfolio_id)
            .scalar_subquery()
        )

        stmt = select(PortfolioTimeseries).where(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.date <= end_date,
            PortfolioTimeseries.epoch == current_epoch_subq
        ).order_by(PortfolioTimeseries.date.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()