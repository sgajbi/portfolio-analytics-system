# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from .database_models import ReprocessingJob

logger = logging.getLogger(__name__)

class ReprocessingJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, job_type: str, payload: Dict[str, Any]) -> ReprocessingJob:
        job = ReprocessingJob(
            job_type=job_type,
            payload=payload,
            status='PENDING'
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        logger.info(f"Created new reprocessing job.", extra={"job_id": job.id, "job_type": job_type})
        return job
        
    async def find_and_claim_jobs(self, job_type: str, batch_size: int) -> List[ReprocessingJob]:
        """
        Finds PENDING jobs, atomically claims them by updating their
        status to PROCESSING, and returns the claimed jobs.
        """
        # This is a simplified version. A more robust implementation would use SKIP LOCKED.
        # For our purposes, this is sufficient as we will run a single worker instance.
        stmt = (
            select(ReprocessingJob)
            .where(ReprocessingJob.status == 'PENDING', ReprocessingJob.job_type == job_type)
            .order_by(ReprocessingJob.created_at.asc())
            .limit(batch_size)
        )
        result = await self.db.execute(stmt)
        jobs_to_claim = result.scalars().all()

        if not jobs_to_claim:
            return []

        claimed_ids = [job.id for job in jobs_to_claim]
        update_stmt = (
            update(ReprocessingJob)
            .where(ReprocessingJob.id.in_(claimed_ids))
            .values(status='PROCESSING', updated_at=datetime.now(timezone.utc), last_attempted_at=datetime.now(timezone.utc))
        )
        await self.db.execute(update_stmt)

        return jobs_to_claim

    async def update_job_status(
        self, job_id: int, status: str, failure_reason: Optional[str] = None
    ) -> None:
        """Updates the status of a specific job, optionally with a failure reason."""
        values_to_update = {
            "status": status,
            "updated_at": datetime.now(timezone.utc)
        }
        if failure_reason:
            values_to_update["failure_reason"] = failure_reason

        stmt = (
            update(ReprocessingJob)
            .where(ReprocessingJob.id == job_id)
            .values(**values_to_update)
        )
        await self.db.execute(stmt)