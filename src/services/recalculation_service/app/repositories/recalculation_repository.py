# src/services/recalculation_service/app/repositories/recalculation_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from sqlalchemy import select, update, text, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import (
    RecalculationJob,
    Transaction,
    PositionHistory,
    DailyPositionSnapshot,
    PositionTimeseries,
    PortfolioTimeseries,
    Cashflow
)
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)


class RecalculationRepository:
    """
    Handles database operations for the RecalculationJob model, including
    atomically claiming jobs for processing and orchestrating data cleanup.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="RecalculationRepository", method="find_and_claim_job")
    async def find_and_claim_job(self) -> Optional[RecalculationJob]:
        """
        Finds the oldest PENDING recalculation job, atomically updates its status
        to 'PROCESSING', and returns the claimed job object. This prevents race
        conditions between multiple service instances.
        """
        query = text("""
            UPDATE recalculation_jobs
            SET status = 'PROCESSING', updated_at = now()
            WHERE id = (
                SELECT id
                FROM recalculation_jobs
                WHERE status = 'PENDING'
                ORDER BY from_date ASC, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING *;
        """)
        
        result = await self.db.execute(query)
        claimed_job_row = result.mappings().first()

        if claimed_job_row:
            logger.info(f"Claimed recalculation job ID {claimed_job_row['id']}.")
            return RecalculationJob(**claimed_job_row)
        
        return None

    @async_timed(repository="RecalculationRepository", method="update_job_status")
    async def update_job_status(self, job_id: int, status: str) -> None:
        """Updates the status of a specific job by its primary key."""
        stmt = (
            update(RecalculationJob)
            .where(RecalculationJob.id == job_id)
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        logger.info(f"Updated status for job ID {job_id} to '{status}'.")

    @async_timed(repository="RecalculationRepository", method="delete_downstream_data")
    async def delete_downstream_data(self, portfolio_id: str, security_id: str, from_date: date) -> None:
        """
        Deletes all calculated data for a specific security in a portfolio from a given
        date onwards. This prepares the system for a clean recalculation.
        """
        logger.info(
            "Deleting downstream data for recalculation",
            extra={"portfolio_id": portfolio_id, "security_id": security_id, "from_date": from_date.isoformat()}
        )
        
        await self.db.execute(delete(PortfolioTimeseries).where(PortfolioTimeseries.portfolio_id == portfolio_id, PortfolioTimeseries.date >= from_date))
        await self.db.execute(delete(PositionTimeseries).where(PositionTimeseries.portfolio_id == portfolio_id, PositionTimeseries.security_id == security_id, PositionTimeseries.date >= from_date))
        await self.db.execute(delete(DailyPositionSnapshot).where(DailyPositionSnapshot.portfolio_id == portfolio_id, DailyPositionSnapshot.security_id == security_id, DailyPositionSnapshot.date >= from_date))
        await self.db.execute(delete(PositionHistory).where(PositionHistory.portfolio_id == portfolio_id, PositionHistory.security_id == security_id, PositionHistory.position_date >= from_date))
        await self.db.execute(delete(Cashflow).where(Cashflow.portfolio_id == portfolio_id, Cashflow.security_id == security_id, Cashflow.cashflow_date >= from_date))

    @async_timed(repository="RecalculationRepository", method="get_all_transactions_for_security")
    async def get_all_transactions_for_security(self, portfolio_id: str, security_id: str) -> List[Transaction]:
        """
        Fetches all transactions for a specific security within a portfolio, ordered chronologically.
        This is required to replay the entire history accurately.
        """
        stmt = (
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id, Transaction.security_id == security_id)
            .order_by(Transaction.transaction_date.asc(), Transaction.id.asc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()