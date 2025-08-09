# services/persistence_service/app/repositories/market_price_repository.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from portfolio_common.database_models import MarketPrice as DBMarketPrice
from portfolio_common.events import MarketPriceEvent

logger = logging.getLogger(__name__)

class MarketPriceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_market_price(self, event: MarketPriceEvent) -> DBMarketPrice:
        """
        Idempotently creates or updates a market price using a native PostgreSQL UPSERT.
        """
        try:
            market_price_data = event.model_dump()

            stmt = pg_insert(DBMarketPrice).values(**market_price_data)

            update_dict = {
                c.name: c for c in stmt.excluded if c.name not in ["id", "security_id", "price_date"]
            }

            # --- FIX: Switched to on_conflict_do_update with index_elements ---
            final_stmt = stmt.on_conflict_do_update(
                index_elements=['security_id', 'price_date'],
                set_=update_dict
            )
            
            await self.db.execute(final_stmt)
            logger.info(f"Successfully staged UPSERT for market price for '{event.security_id}' on '{event.price_date}'.")

            return DBMarketPrice(**market_price_data)
        except Exception as e:
            logger.error(f"Failed to stage UPSERT for market price for '{event.security_id}' on '{event.price_date}': {e}", exc_info=True)
            raise