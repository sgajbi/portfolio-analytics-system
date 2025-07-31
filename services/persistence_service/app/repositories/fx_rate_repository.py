import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert # Import pg_insert

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
        The unique constraint for FxRate is ('from_currency', 'to_currency', 'rate_date').
        """
        insert_dict = {
            "from_currency": event.from_currency,
            "to_currency": event.to_currency,
            "rate_date": event.rate_date,
            "rate": event.rate,
        }

        stmt = pg_insert(DBFxRate).values(**insert_dict)
        
        # Define what to update if a conflict on the unique composite key occurs.
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['from_currency', 'to_currency', 'rate_date'],
            set_={
                'rate': stmt.excluded.rate,
                'updated_at': stmt.excluded.updated_at # Ensure updated_at is refreshed
            }
        ).returning(DBFxRate) # Return the inserted or updated row

        try:
            result = self.db.execute(on_conflict_stmt).scalar_one()
            self.db.commit()
            logger.info(
                f"FX rate for '{result.from_currency}-{result.to_currency}' on "
                f"'{result.rate_date}' successfully upserted."
            )
            return result
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}", exc_info=True)
            raise