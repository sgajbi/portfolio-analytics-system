import logging
from sqlalchemy.orm import Session
from portfolio_common.database_models import MarketPrice as DBMarketPrice
from portfolio_common.events import MarketPriceEvent

logger = logging.getLogger(__name__)

class MarketPriceRepository:
    """
    Handles database operations for the MarketPrice model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_market_price(self, event: MarketPriceEvent) -> DBMarketPrice:
        """
        Idempotently creates or updates a market price using a
        get-then-update/create pattern.
        """
        try:
            db_price = self.db.query(DBMarketPrice).filter(
                DBMarketPrice.security_id == event.security_id,
                DBMarketPrice.price_date == event.price_date
            ).first()

            if db_price:
                # Update existing
                db_price.price = event.price
                db_price.currency = event.currency
                logger.info(f"Price for '{event.security_id}' on {event.price_date} found, staging for update.")
            else:
                # Create new
                db_price = DBMarketPrice(**event.model_dump(by_alias=True))
                self.db.add(db_price)
                logger.info(f"Price for '{event.security_id}' on {event.price_date} not found, staging for creation.")

            return db_price
        except Exception as e:
            logger.error(f"Failed to stage upsert for market price for '{event.security_id}' on '{event.price_date}': {e}", exc_info=True)
            raise