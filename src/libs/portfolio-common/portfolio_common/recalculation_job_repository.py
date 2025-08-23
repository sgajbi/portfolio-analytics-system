# src/libs/portfolio-common/portfolio_common/recalculation_job_repository.py
import logging
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import RecalculationJob

logger = logging.getLogger(__name__)

class RecalculationJobRepository:
    """
    Handles database operations for creating and managing RecalculationJob records.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_job(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        from_date: date,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Idempotently creates or updates a recalculation job.

        If a job for the (portfolio_id, security_id) pair does not exist, it creates one.
        If a job already exists, it updates it by setting the status back to 'PENDING'
        and ensuring the 'from_date' is the earliest of the existing and new dates.
        This efficiently coalesces multiple reprocessing requests into a single job.
        """
        try:
            job_data = {
                "portfolio_id": portfolio_id,
                "security_id": security_id,
                "from_date": from_date,
                "status": "PENDING",
                "correlation_id": correlation_id,
            }

            stmt = pg_insert(RecalculationJob).values(**job_data)

            update_dict = {
                "status": "PENDING",
                "from_date": func.least(RecalculationJob.from_date, stmt.excluded.from_date),
                "correlation_id": stmt.excluded.correlation_id,
                "updated_at": func.now(),
            }

            final_stmt = stmt.on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id'],
                set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.debug(
                "Staged upsert for recalculation job",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "from_date": from_date,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to stage upsert for recalculation job",
                extra={
                    "portfolio_id": portfolio_id,
                    "security_id": security_id,
                    "from_date": from_date,
                },
                exc_info=True,
            )
            raise