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
        Creates a new market price.
        
        If a price for the given security_id and price_date already exists,
        the database's unique constraint will raise an IntegrityError, which is
        caught and handled gracefully. This makes the operation idempotent.
        """
        db_market_price = DBMarketPrice(
            security_id=event.security_id,
            price_date=event.price_date,
            price=event.price,
            currency=event.currency,
        )
        
        try:
            self.db.add(db_market_price)
            self.db.commit()
            self.db.refresh(db_market_price)
            logger.info(f"Market price for '{db_market_price.security_id}' on '{db_market_price.price_date}' successfully inserted.")
            return db_market_price
        except IntegrityError:
            self.db.rollback()
            logger.warning(
                f"Market price for '{event.security_id}' on '{event.price_date}' already exists. "
                "Skipping creation due to unique constraint."
            )
            return self.db.query(DBMarketPrice).filter(
                DBMarketPrice.security_id == event.security_id,
                DBMarketPrice.price_date == event.price_date
            ).first()