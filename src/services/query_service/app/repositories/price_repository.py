# services/query-service/app/repositories/price_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import MarketPrice

logger = logging.getLogger(__name__)


class MarketPriceRepository:
    """
    Handles read-only database queries for market price data.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_prices(
        self, security_id: str, start_date: Optional[date] = None, end_date: Optional[date] = None
    ) -> List[MarketPrice]:
        """
        Retrieves a list of market prices for a security, with optional
        date range filtering.
        """
        stmt = select(MarketPrice).filter_by(security_id=security_id)

        if start_date:
            stmt = stmt.filter(MarketPrice.price_date >= start_date)

        if end_date:
            stmt = stmt.filter(MarketPrice.price_date <= end_date)

        results = await self.db.execute(stmt.order_by(MarketPrice.price_date.asc()))
        prices = results.scalars().all()
        logger.info(f"Found {len(prices)} prices for security '{security_id}' with given filters.")
        return prices
