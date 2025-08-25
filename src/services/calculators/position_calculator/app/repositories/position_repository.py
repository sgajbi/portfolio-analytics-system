# services/calculators/position_calculator/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import (
    PositionHistory, Transaction, DailyPositionSnapshot, BusinessDate
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles all database interactions for position calculation.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PositionRepository", method="get_latest_business_date")
    async def get_latest_business_date(self) -> Optional[date]:
        """
        Finds the most recent date present in the dedicated business_dates table.
        """
        stmt = select(func.max(BusinessDate.date))
        result = await self.db.execute(stmt)
        latest_date = result.scalar_one_or_none()
        return latest_date

    @async_timed(repository="PositionRepository", method="get_last_position_before")
    async def get_last_position_before(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> Optional[PositionHistory]:
        stmt = select(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date < a_date
        ).order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    @async_timed(repository="PositionRepository", method="get_transactions_on_or_after")
    async def get_transactions_on_or_after(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Transaction]:
        stmt = select(Transaction).filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.security_id == security_id,
            func.date(Transaction.transaction_date) >= a_date
        ).order_by(Transaction.transaction_date.asc(), Transaction.id.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="PositionRepository", method="delete_positions_from")
    async def delete_positions_from(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> int:
        stmt = delete(PositionHistory).where(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date >= a_date
        )
        result = await self.db.execute(stmt)
        deleted_count = result.rowcount or 0
        logger.info(
            f"Deleted {deleted_count} stale position records "
            f"for {security_id} from {a_date} onward."
        )
        return deleted_count

    @async_timed(repository="PositionRepository", method="save_positions")
    async def save_positions(self, positions: List[PositionHistory]):
        if not positions:
            logger.debug("No new positions to save.")
            return

        self.db.add_all(positions)
        await self.db.flush()
        logger.info(f"Staged and flushed {len(positions)} new position records for saving.")