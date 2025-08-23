# src/services/recalculation_service/app/repositories/recalculation_repository.py
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import RecalculationJob
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)


class RecalculationRepository:
    """
    Handles database operations for the RecalculationJob model, including
    atomically claiming jobs for processing.
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
        # This raw SQL query uses 'FOR UPDATE SKIP LOCKED' which is a PostgreSQL-specific
        # feature for implementing a work queue. It finds the first available (unlocked)
        # row, locks it, and updates it, all within a single atomic transaction.
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
            logger.info(f"Claimed recalculation job ID {claimed_job_row.id}.")
            return RecalculationJob(**claimed_job_row)
        
        return None

    @async_timed(repository="RecalculationRepository", method="update_job_status")
    async def update_job_status(self, job_id: int, status: str) -> None:
        """Updates the status of a specific job by its primary key."""
        stmt = (
            update(RecalculationJob)
            .where(RecalculationJob.id == job_id)
            .values(status=status, updated_at=func.now())
        )
        await self.db.execute(stmt)
        logger.info(f"Updated status for job ID {job_id} to '{status}'.")

    @async_timed(repository="RecalculationRepository", method="find_and_reset_stale_jobs")
    async def find_and_reset_stale_jobs(self, timeout_minutes: int = 30) -> int:
        """
        Finds jobs stuck in 'PROCESSING' state for longer than the timeout
        and resets them to 'PENDING' for reprocessing.
        """
        stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        
        stmt = (
            update(RecalculationJob)
            .where(
                RecalculationJob.status == 'PROCESSING',
                RecalculationJob.updated_at < stale_threshold
            )
            .values(status='PENDING')
        )
        
        result = await self.db.execute(stmt)
        reset_count = result.rowcount or 0
        
        if reset_count > 0:
            logger.warning(f"Reset {reset_count} stale recalculation jobs from 'PROCESSING' to 'PENDING'.")
            
        return reset_count