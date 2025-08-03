# services/persistence_service/app/repositories/fx_rate_repository.py
import logging
from sqlalchemy.orm import Session
from portfolio_common.database_models import FxRate as DBFxRate
from portfolio_common.events import FxRateEvent

logger = logging.getLogger(__name__)

class FxRateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_fx_rate(self, event: FxRateEvent) -> DBFxRate:
        try:
            db_rate = self.db.query(DBFxRate).filter(
                DBFxRate.from_currency == event.from_currency,
                DBFxRate.to_currency == event.to_currency,
                DBFxRate.rate_date == event.rate_date
            ).first()

            fx_rate_data = event.model_dump()

            if db_rate:
                for key, value in fx_rate_data.items():
                    setattr(db_rate, key, value)
                logger.info(f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} found, staging for update.")
            else:
                db_rate = DBFxRate(**fx_rate_data)
                self.db.add(db_rate)
                logger.info(f"FX Rate for '{event.from_currency}-{event.to_currency}' on {event.rate_date} not found, staging for creation.")

            return db_rate
        except Exception as e:
            logger.error(f"Failed to stage upsert for FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}': {e}", exc_info=True)
            raise