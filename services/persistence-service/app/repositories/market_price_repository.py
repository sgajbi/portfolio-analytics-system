import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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
        Creates and adds a new market price to the session.
        The calling function is responsible for committing the transaction.
        If a price for the given security_id and price_date already exists,
        this will do nothing and the existing record can be queried if needed.
        """
        
        # Check if the record already exists to make the operation idempotent
        existing_price = self.db.query(DBMarketPrice).filter(
            DBMarketPrice.security_id == event.security_id,
            DBMarketPrice.price_date == event.price_date
        ).first()

        if existing_price:
            logger.warning(
                f"Market price for '{event.security_id}' on '{event.price_date}' already exists. "
                "Skipping creation."
            )
            return existing_price

        db_market_price = DBMarketPrice(
            security_id=event.security_id,
            price_date=event.price_date,
            price=event.price,
            currency=event.currency,
        )
        
        self.db.add(db_market_price)
        logger.info(f"Market price for '{db_market_price.security_id}' on '{db_market_price.price_date}' added to session.")
        return db_market_price