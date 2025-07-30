import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert # Import pg_insert

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
        Idempotently creates a new market price or updates an existing one.
        Uses PostgreSQL's ON CONFLICT DO UPDATE to handle potential duplicates.
        """
        insert_dict = {
            "security_id": event.security_id,
            "price_date": event.price_date,
            "price": event.price,
            "currency": event.currency,
        }

        # The unique constraint for MarketPrice is ('security_id', 'price_date').
        stmt = pg_insert(DBMarketPrice).values(**insert_dict)
        
        # Define what to update if a conflict on ('security_id', 'price_date') occurs.
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['security_id', 'price_date'],
            set_={
                'price': stmt.excluded.price,
                'currency': stmt.excluded.currency,
                'updated_at': stmt.excluded.updated_at # Ensure updated_at is refreshed
            }
        ).returning(DBMarketPrice) # Return the inserted or updated row

        try:
            result = self.db.execute(on_conflict_stmt).scalar_one()
            # Note: The commit is handled by the calling consumer's transaction block (e.g., MarketPriceConsumer).
            # If this method is called outside a transaction, it would need its own commit.
            # For this service, the consumer usually manages the session.commit().
            logger.info(f"Market price for '{result.security_id}' on '{result.price_date}' successfully upserted into DB.")
            return result
        except Exception as e:
            self.db.rollback() # Rollback if an error occurs within this method's context
            logger.error(f"Failed to upsert market price for '{event.security_id}' on '{event.price_date}': {e}", exc_info=True)
            raise