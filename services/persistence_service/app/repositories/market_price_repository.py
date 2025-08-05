# services/persistence_service/app/repositories/market_price_repository.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from portfolio_common.database_models import MarketPrice as DBMarketPrice
from portfolio_common.events import MarketPriceEvent

logger = logging.getLogger(__name__)

class MarketPriceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_market_price(self, event: MarketPriceEvent) -> DBMarketPrice:
        try:
            stmt = select(DBMarketPrice).filter_by(
                security_id=event.security_id,
                price_date=event.price_date
            )
            result = await self.db.execute(stmt)
            db_price = result.scalars().first()

            market_price_data = event.model_dump()

            if db_price:
                for key, value in market_price_data.items():
                    setattr(db_price, key, value)
                logger.info(f"Price for '{event.security_id}' on {event.price_date} found, staging for update.")
            else:
                db_price = DBMarketPrice(**market_price_data)
                self.db.add(db_price)
                logger.info(f"Price for '{event.security_id}' on {event.price_date} not found, staging for creation.")

            return db_price
        except Exception as e:
            logger.error(f"Failed to stage upsert for market price for '{event.security_id}' on '{event.price_date}': {e}", exc_info=True)
            raise