# services/calculators/position_calculator/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Transaction

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles all database interactions for position calculation.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_last_position_before(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> Optional[PositionHistory]:
        """
        Fetches most recent position before given date.
        This is used as the anchor for recalculation.
        """
        stmt = select(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date < a_date
        ).order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
        
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_transactions_on_or_after(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Transaction]:
        """
        Retrieves all transactions for security on or after given date.
        Uses full timestamp ordering to maintain sequence.
        """
        stmt = select(Transaction).filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.security_id == security_id,
            func.date(Transaction.transaction_date) >= a_date
        ).order_by(Transaction.transaction_date.asc(), Transaction.id.asc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def delete_positions_from(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> int:
        """
        Deletes all position history records for a security from given date onward.
        Returns number of deleted rows.
        """
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

    async def save_positions(self, positions: List[PositionHistory]):
        """
        Bulk saves new position history records.
        """
        if not positions:
            logger.debug("No new positions to save.")
            return

        self.db.add_all(positions)
        await self.db.flush()
        logger.info(f"Staged and flushed {len(positions)} new position records for saving.")