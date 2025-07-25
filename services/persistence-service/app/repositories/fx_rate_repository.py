import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
        Creates a new FX rate.
        
        If a rate for the given currency pair and date already exists,
        the database's unique constraint will raise an IntegrityError, which is
        caught and handled gracefully. This makes the operation idempotent.
        """
        db_fx_rate = DBFxRate(
            from_currency=event.from_currency,
            to_currency=event.to_currency,
            rate_date=event.rate_date,
            rate=event.rate,
        )
        
        try:
            self.db.add(db_fx_rate)
            self.db.commit()
            self.db.refresh(db_fx_rate)
            logger.info(
                f"FX rate for '{db_fx_rate.from_currency}-{db_fx_rate.to_currency}' on "
                f"'{db_fx_rate.rate_date}' successfully inserted."
            )
            return db_fx_rate
        except IntegrityError:
            self.db.rollback()
            logger.warning(
                f"FX rate for '{event.from_currency}-{event.to_currency}' on '{event.rate_date}' already exists. "
                "Skipping creation due to unique constraint."
            )
            return self.db.query(DBFxRate).filter(
                DBFxRate.from_currency == event.from_currency,
                DBFxRate.to_currency == event.to_currency,
                DBFxRate.rate_date == event.rate_date
            ).first()