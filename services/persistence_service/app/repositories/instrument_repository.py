import logging
from sqlalchemy.orm import Session
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
        Idempotently creates or updates an instrument using a
        get-then-update/create pattern based on security_id.
        """
        try:
            db_instrument = self.db.query(DBInstrument).filter(DBInstrument.security_id == event.security_id).first()
            
            if db_instrument:
                # Update existing
                db_instrument.name = event.name
                db_instrument.isin = event.isin
                db_instrument.currency = event.currency
                db_instrument.product_type = event.product_type
                logger.info(f"Instrument '{event.security_id}' found, staging for update.")
            else:
                # Create new
                db_instrument = DBInstrument(**event.model_dump(by_alias=True))
                self.db.add(db_instrument)
                logger.info(f"Instrument '{event.security_id}' not found, staging for creation.")

            return db_instrument
        except Exception as e:
            logger.error(f"Failed to stage upsert for instrument '{event.security_id}': {e}", exc_info=True)
            raise