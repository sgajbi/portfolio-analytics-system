# src/services/query_service/app/repositories/performance_repository.py
import logging
from typing import List
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import PortfolioTimeseries
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
        Fetches the raw, daily portfolio_timeseries data required as input
        for on-the-fly performance calculations.
        """
        stmt = select(PortfolioTimeseries).where(
            PortfolioTimeseries.portfolio_id == portfolio_id,
            PortfolioTimeseries.date >= start_date,
            PortfolioTimeseries.date <= end_date
        ).order_by(PortfolioTimeseries.date.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()