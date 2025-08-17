# src/services/calculators/performance_calculator_service/app/repositories/performance_repository.py
import logging
from typing import List
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.database_models import DailyPerformanceMetric
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class PerformanceRepository:
    """
    Handles all database operations for the DailyPerformanceMetric model.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="PerformanceRepository", method="upsert_daily_metrics")
    async def upsert_daily_metrics(self, metrics: List[DailyPerformanceMetric]):
        """
        Idempotently inserts or updates a list of daily performance metrics
        using a native PostgreSQL UPSERT (INSERT ... ON CONFLICT DO UPDATE).
        """
        if not metrics:
            return

        try:
            insert_data = [
                {
                    "portfolio_id": metric.portfolio_id,
                    "date": metric.date,
                    "return_basis": metric.return_basis,
                    "linking_factor": metric.linking_factor,
                    "daily_return_pct": metric.daily_return_pct,
                }
                for metric in metrics
            ]

            stmt = pg_insert(DailyPerformanceMetric).values(insert_data)

            # Define the update statement for the conflict case.
            # This ensures that values from the attempted insert (the 'excluded' table)
            # are used to update the existing row.
            update_stmt = stmt.on_conflict_do_update(
                index_elements=['portfolio_id', 'date', 'return_basis'],
                set_={
                    'linking_factor': stmt.excluded.linking_factor,
                    'daily_return_pct': stmt.excluded.daily_return_pct,
                    'updated_at': func.now(),
                }
            )
            await self.db.execute(update_stmt)
            logger.info(f"Successfully staged UPSERT for {len(metrics)} performance metric records.")
        except Exception as e:
            logger.error(f"Failed to stage UPSERT for performance metrics: {e}", exc_info=True)
            raise