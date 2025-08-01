import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import Instrument as DBInstrument
from portfolio_common.events import InstrumentEvent

logger = logging.getLogger(__name__)

class InstrumentRepository:
    """
    Handles database operations for the Instrument model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_instrument(self, event: InstrumentEvent) -> DBInstrument:
        """
        Idempotently creates a new instrument or updates an existing one based on security_id.
        This operation leverages PostgreSQL's ON CONFLICT DO UPDATE (UPSERT).
        """
        insert_dict = {
            "security_id": event.security_id,
            "name": event.name,
            "isin": event.isin,
            "currency": event.currency,
            "product_type": event.product_type,
        }

        stmt = pg_insert(DBInstrument).values(**insert_dict)
        
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['security_id'],
            set_={
                'name': stmt.excluded.name,
                'isin': stmt.excluded.isin,
                'currency': stmt.excluded.currency,
                'product_type': stmt.excluded.product_type,
                'updated_at': stmt.excluded.updated_at
            }
        ).returning(DBInstrument)

        try:
            result = self.db.execute(on_conflict_stmt).scalar_one()
            # COMMIT AND ROLLBACK REMOVED
            logger.info(f"Instrument '{result.security_id}' successfully staged for upsert.")
            return result
        except Exception as e:
            logger.error(f"Failed to stage upsert for instrument '{event.security_id}': {e}", exc_info=True)
            raise