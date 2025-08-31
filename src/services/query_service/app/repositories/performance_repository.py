# src/services/query_service/app/repositories/performance_repository.py
import logging
from typing import List
from datetime import date
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import PortfolioTimeseries, PositionState, PositionTimeseries
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class PerformanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PerformanceRepository", method="get_position_timeseries_for_range")
    async def get_position_timeseries_for_range(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: date,
        end_date: date,
    ) -> List[PositionTimeseries]:
        """
        Fetches the raw, daily position_timeseries data required for performance
        calculations, ensuring it only selects data from the security's current epoch.
        """
        stmt = (
            select(PositionTimeseries)
            .join(
                PositionState,
                and_(
                    PositionTimeseries.portfolio_id == PositionState.portfolio_id,
                    PositionTimeseries.security_id == PositionState.security_id,
                    PositionTimeseries.epoch == PositionState.epoch,
                )
            )
            .where(
                PositionTimeseries.portfolio_id == portfolio_id,
                PositionTimeseries.security_id == security_id,
                PositionTimeseries.date.between(start_date, end_date)
            )
            .order_by(PositionTimeseries.date.asc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

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