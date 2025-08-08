# services/persistence_service/app/repositories/fx_rate_repository.py
import logging
from typing import Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.events import FxRateEvent

logger = logging.getLogger(__name__)

class FxRateRepository:
    """
    Repository for upserting FX rate records into the database.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_fx_rate(self, event: FxRateEvent) -> DBFxRate:
        """
        Idempotently creates or updates an FX rate using a native PostgreSQL UPSERT.
        """
        try:
            fx_rate_data = event.model_dump()
            
            stmt = pg_insert(DBFxRate).values(**fx_rate_data)
            
            update_dict = {
                c.name: c for c in stmt.excluded if c.name not in ["id", "from_currency", "to_currency", "rate_date"]
            }

            # Use the unique constraint name for conflict resolution
            final_stmt = stmt.on_conflict_on_constraint(
                constraint='_currency_pair_date_uc',
                set_=update_dict
            )

            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date}.")

            return DBFxRate(**fx_rate_data)
        except Exception as e:
            logger.error(f"Failed to stage UPSERT for FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}", exc_info=True)
            raise