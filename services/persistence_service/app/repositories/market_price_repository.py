# services/persistence_service/app/repositories/market_price_repository.py
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

            market_price_data = event.model_dump()

            if db_price:
                # Update existing
                for key, value in market_price_data.items():
                    setattr(db_price, key, value)
                logger.info(f"Price for '{event.security_id}' on {event.price_date} found, staging for update.")
            else:
                # Create new
                db_price = DBMarketPrice(**market_price_data)
                self.db.add(db_price)
                logger.info(f"Price for '{event.security_id}' on {event.price_date} not found, staging for creation.")

            return db_price
        except Exception as e:
            logger.error(f"Failed to stage upsert for market price for '{event.security_id}' on '{event.price_date}': {e}", exc_info=True)
            raise