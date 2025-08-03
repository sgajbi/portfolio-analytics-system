# services/persistence_service/app/repositories/instrument_repository.py
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
            
            # Use model_dump() without by_alias to get Python-native field names
            instrument_data = event.model_dump()
            
            if db_instrument:
                # Update existing
                for key, value in instrument_data.items():
                    setattr(db_instrument, key, value)
                logger.info(f"Instrument '{event.security_id}' found, staging for update.")
            else:
                # Create new
                db_instrument = DBInstrument(**instrument_data)
                self.db.add(db_instrument)
                logger.info(f"Instrument '{event.security_id}' not found, staging for creation.")

            return db_instrument
        except Exception as e:
            logger.error(f"Failed to stage upsert for instrument '{event.security_id}': {e}", exc_info=True)
            raise