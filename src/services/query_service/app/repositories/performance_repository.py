# src/services/query_service/app/repositories/performance_repository.py
import logging
from typing import List
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import DailyPerformanceMetric
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class PerformanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PerformanceRepository", method="get_daily_metrics")
    async def get_daily_metrics(
        self,
        portfolio_id: str,
        start_date: date,
        end_date: date,
        metric_basis: str
    ) -> List[DailyPerformanceMetric]:
        """
        Fetches daily performance metrics (linking factors) for a given portfolio
        and date range.
        """
        stmt = select(DailyPerformanceMetric).where(
            DailyPerformanceMetric.portfolio_id == portfolio_id,
            DailyPerformanceMetric.date >= start_date,
            DailyPerformanceMetric.date <= end_date,
            DailyPerformanceMetric.return_basis == metric_basis
        ).order_by(DailyPerformanceMetric.date.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()