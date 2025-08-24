# src/services/recalculation_service/app/repositories/recalculation_repository.py
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel

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


class CoalescedRecalculationJob(BaseModel):
    """A data structure to hold a group of claimed jobs that have been coalesced."""
    earliest_from_date: date
    claimed_jobs: List[RecalculationJob]

    class Config:
        arbitrary_types_allowed = True


class RecalculationRepository:
    """
    Handles database operations for the RecalculationJob model, including
    atomically claiming jobs for processing and orchestrating data cleanup.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="RecalculationRepository", method="find_and_claim_coalesced_job")
    async def find_and_claim_coalesced_job(self) -> Optional[CoalescedRecalculationJob]:
        """
        Atomically finds the oldest pending job, then finds and claims all other
        pending jobs for the same (portfolio_id, security_id) pair using a single query.
        Coalesces them into a single unit of work.
        """
        # CTE to find the identity of the single oldest job to process.
        oldest_job_cte = (
            select(
                RecalculationJob.portfolio_id,
                RecalculationJob.security_id
            )
            .where(RecalculationJob.status == 'PENDING')
            .order_by(RecalculationJob.from_date.asc(), RecalculationJob.created_at.asc())
            .limit(1)
            .cte('oldest_job')
        )

        # Main query to select and lock all related pending jobs based on the CTE's result.
        all_related_jobs_stmt = (
            select(RecalculationJob)
            .where(
                RecalculationJob.status == 'PENDING',
                RecalculationJob.portfolio_id == select(oldest_job_cte.c.portfolio_id).scalar_subquery(),
                RecalculationJob.security_id == select(oldest_job_cte.c.security_id).scalar_subquery()
            )
            .with_for_update(skip_locked=True)
        )

        result = await self.db.execute(all_related_jobs_stmt)
        all_related_jobs = result.scalars().all()

        if not all_related_jobs:
            return None

        # Coalesce, Update status to PROCESSING for all claimed jobs
        job_ids_to_claim = [job.id for job in all_related_jobs]
        earliest_from_date = min(job.from_date for job in all_related_jobs)

        update_stmt = (
            update(RecalculationJob)
            .where(RecalculationJob.id.in_(job_ids_to_claim))
            .values(status='PROCESSING', updated_at=func.now())
        )
        await self.db.execute(update_stmt)

        logger.info(f"Claimed {len(all_related_jobs)} recalculation jobs for ({all_related_jobs[0].portfolio_id}, {all_related_jobs[0].security_id}).")

        # Return the coalesced job details
        return CoalescedRecalculationJob(
            earliest_from_date=earliest_from_date,
            claimed_jobs=all_related_jobs
        )

    @async_timed(repository="RecalculationRepository", method="update_job_status")
    async def update_job_status(self, job_ids: List[int], status: str) -> None:
        """Updates the status of a list of jobs by their primary keys."""
        if not job_ids:
            return
            
        stmt = (
            update(RecalculationJob)
            .where(RecalculationJob.id.in_(job_ids))
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
        logger.info(f"Updated status for {len(job_ids)} job IDs to '{status}'.")

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