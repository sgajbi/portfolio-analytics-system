import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.events import FxRateEvent

logger = logging.getLogger(__name__)

class FxRateRepository:
    """
    Handles database operations for the FxRate model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_fx_rate(self, event: FxRateEvent) -> DBFxRate:
        """
        Idempotently creates a new FX rate or updates an existing one.
        Uses PostgreSQL's ON CONFLICT DO UPDATE to handle potential duplicates.
        """
        insert_dict = {
            "from_currency": event.from_currency,
            "to_currency": event.to_currency,
            "rate_date": event.rate_date,
            "rate": event.rate,
        }

        stmt = pg_insert(DBFxRate).values(**insert_dict)
        
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['from_currency', 'to_currency', 'rate_date'],
            set_={
                'rate': stmt.excluded.rate,
                'updated_at': stmt.excluded.updated_at
            }
        ).returning(DBFxRate)

        try:
            result = self.db.execute(on_conflict_stmt).scalar_one()
            # COMMIT AND ROLLBACK REMOVED
            logger.info(
                f"FX rate for '{result.from_currency}-{result.to_currency}' on "
                f"'{result.rate_date}' successfully staged for upsert."
            )
            return result
        except Exception as e:
            logger.error(f"Failed to stage upsert for FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}", exc_info=True)
            raise