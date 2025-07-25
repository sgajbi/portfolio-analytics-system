import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
        Creates a new instrument or returns the existing one if the security_id already exists.
        This operation is idempotent.
        """
        # Check if the instrument already exists
        existing_instrument = self.db.query(DBInstrument).filter(
            DBInstrument.security_id == event.security_id
        ).first()

        if existing_instrument:
            logger.info(f"Instrument with security_id '{event.security_id}' already exists. Skipping creation.")
            return existing_instrument
        
        # Create a new instrument if it doesn't exist
        db_instrument = DBInstrument(
            security_id=event.security_id,
            name=event.name,
            isin=event.isin,
            currency=event.currency,
            product_type=event.product_type,
        )
        
        try:
            self.db.add(db_instrument)
            self.db.commit()
            self.db.refresh(db_instrument)
            logger.info(f"Instrument '{db_instrument.security_id}' successfully inserted into DB.")
            return db_instrument
        except IntegrityError:
            self.db.rollback()
            logger.warning(f"Race condition: Instrument '{event.security_id}' was inserted by another process. Fetching existing.")
            return self.db.query(DBInstrument).filter(
                DBInstrument.security_id == event.security_id
            ).first()