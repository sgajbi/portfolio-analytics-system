# services/calculators/position_calculator/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.database_models import (
    PositionHistory, Transaction, DailyPositionSnapshot, BusinessDate, PortfolioValuationJob,
    RecalculationJob
)
from portfolio_common.utils import async_timed
from portfolio_common.recalculation_job_repository import RecalculationJobRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository

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

    @async_timed(repository="PositionRepository", method="upsert_valuation_job")
    async def upsert_valuation_job(
        self,
        portfolio_id: str,
        security_id: str,
        valuation_date: date,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Idempotently creates or updates a valuation job by delegating to the common repository.
        """
        repo = ValuationJobRepository(self.db)
        await repo.upsert_job(
            portfolio_id=portfolio_id,
            security_id=security_id,
            valuation_date=valuation_date,
            correlation_id=correlation_id
        )
        logger.info(f"Staged upsert for VALUATION job for {security_id} on {valuation_date}")

    @async_timed(repository="PositionRepository", method="create_recalculation_job")
    async def create_recalculation_job(
        self,
        portfolio_id: str,
        security_id: str,
        from_date: date,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Creates a new recalculation job by delegating to the common repository.
        """
        repo = RecalculationJobRepository(self.db)
        await repo.create_job(
            portfolio_id=portfolio_id,
            security_id=security_id,
            from_date=from_date,
            correlation_id=correlation_id,
        )
        logger.info(f"Staged new RECALCULATION job for {security_id} from {from_date}")

    @async_timed(repository="PositionRepository", method="find_open_security_ids_as_of")
    async def find_open_security_ids_as_of(self, portfolio_id: str, a_date: date) -> List[str]:
        """
        Finds all security_ids in a portfolio that had a non-zero quantity
        based on the last known snapshot on or before the given date.
        """
        latest_snapshot_subq = (
            select(
                DailyPositionSnapshot.security_id,
                DailyPositionSnapshot.quantity,
                func.row_number().over(
                    partition_by=DailyPositionSnapshot.security_id,
                    order_by=DailyPositionSnapshot.date.desc()
                ).label("rn")
            )
            .where(
                DailyPositionSnapshot.portfolio_id == portfolio_id,
                DailyPositionSnapshot.date <= a_date
            )
            .subquery('latest_snapshot')
        )

        stmt = (
            select(latest_snapshot_subq.c.security_id)
            .where(
                latest_snapshot_subq.c.rn == 1,
                latest_snapshot_subq.c.quantity != 0
            )
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

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