# src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py
import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from .database_models import ReprocessingJob

logger = logging.getLogger(__name__)

class ReprocessingJobRepository:
    """
    Handles database operations for creating and managing ReprocessingJob records.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, job_type: str, payload: Dict[str, Any]) -> ReprocessingJob:
        """
        Creates and persists a new reprocessing job.
        """
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