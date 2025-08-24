# src/libs/portfolio-common/portfolio_common/recalculation_job_repository.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy import func, select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import RecalculationJob

logger = logging.getLogger(__name__)

class RecalculationJobRepository:
    """
    Handles database operations for creating and managing RecalculationJob records.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        from_date: date,
        correlation_id: Optional[str] = None,
    ) -> RecalculationJob:
        """
        Creates a new recalculation job by inserting a new record.
        Returns the created job object.
        """
        try:
            job = RecalculationJob(
                portfolio_id=portfolio_id,
                security_id=security_id,
                from_date=from_date,
                status="PENDING",
                correlation_id=correlation_id,
            )
            self.db.add(job)
            await self.db.flush()
            logger.debug(
                "Staged new recalculation job for insertion",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "from_date": from_date,
                },
            )
            return job
        except Exception as e:
            logger.error(
                "Failed to stage new recalculation job",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "from_date": from_date,
                },
                exc_info=True,
            )
            raise

    async def is_job_processing(self, portfolio_id: str, security_id: str) -> bool:
        """
        Checks if a recalculation job is currently in the 'PROCESSING' state
        for a specific portfolio and security.
        """
        stmt = select(
            exists().where(
                RecalculationJob.portfolio_id == portfolio_id,
                RecalculationJob.security_id == security_id,
                RecalculationJob.status == 'PROCESSING'
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar()