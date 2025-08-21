# src/services/persistence_service/app/repositories/business_date_repository.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.events import BusinessDateEvent
from portfolio_common.database_models import BusinessDate as DBBusinessDate

logger = logging.getLogger(__name__)

class BusinessDateRepository:
    """
    Handles database operations for the BusinessDate model.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_business_date(self, event: BusinessDateEvent) -> None:
        """
        Idempotently creates a business date using a native PostgreSQL
        UPSERT (INSERT ... ON CONFLICT DO NOTHING).
        """
        try:
            business_date_data = { "date": event.business_date }
            
            stmt = pg_insert(DBBusinessDate).values(
                **business_date_data
            )

            # If the date already exists, do nothing. This makes the operation idempotent.
            final_stmt = stmt.on_conflict_do_nothing(
                index_elements=['date']
            )
            
            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for business date '{event.business_date}'.")

        except Exception as e:
            logger.error(f"Failed to stage UPSERT for business date '{event.business_date}': {e}", exc_info=True)
            raise