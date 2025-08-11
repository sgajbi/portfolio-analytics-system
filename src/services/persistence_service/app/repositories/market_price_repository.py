# services/persistence_service/app/repositories/market_price_repository.py
import logging
from datetime import date
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from portfolio_common.database_models import MarketPrice as DBMarketPrice, DailyPositionSnapshot
from portfolio_common.events import MarketPriceEvent

logger = logging.getLogger(__name__)

class MarketPriceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_portfolios_holding_security_on_date(self, security_id: str, price_date: date) -> List[str]:
        """
        Finds all unique portfolio_ids that have a non-zero position in a given
        security on a specific date by querying the daily snapshots.
        """
        stmt = (
            select(DailyPositionSnapshot.portfolio_id)
            .where(
                DailyPositionSnapshot.security_id == security_id,
                DailyPositionSnapshot.date == price_date,
                DailyPositionSnapshot.quantity > 0
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        portfolio_ids = result.scalars().all()
        logger.info(f"Found {len(portfolio_ids)} portfolios holding '{security_id}' on {price_date}.")
        return portfolio_ids

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