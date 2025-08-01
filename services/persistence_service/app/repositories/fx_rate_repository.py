import logging
from sqlalchemy.orm import Session
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
        Idempotently creates or updates an FX rate using a
        get-then-update/create pattern.
        """
        try:
            db_rate = self.db.query(DBFxRate).filter(
                DBFxRate.from_currency == event.from_currency,
                DBFxRate.to_currency == event.to_currency,
                DBFxRate.rate_date == event.rate_date
            ).first()

            if db_rate:
                # Update existing
                db_rate.rate = event.rate
                logger.info(f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} found, staging for update.")
            else:
                # Create new
                db_rate = DBFxRate(**event.model_dump(by_alias=True))
                self.db.add(db_rate)
                logger.info(f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} not found, staging for creation.")

            return db_rate
        except Exception as e:
            logger.error(f"Failed to stage upsert for FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}", exc_info=True)
            raise