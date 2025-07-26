import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from portfolio_common.database_models import MarketPrice

logger = logging.getLogger(__name__)

class MarketPriceRepository:
    """
    Handles read-only database queries for market price data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_prices(
        self,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[MarketPrice]:
        """
        Retrieves a list of market prices for a security, with optional
        date range filtering.
        """
        query = self.db.query(MarketPrice).filter(
            MarketPrice.security_id == security_id
        )

        if start_date:
            query = query.filter(MarketPrice.price_date >= start_date)
        
        if end_date:
            query = query.filter(MarketPrice.price_date <= end_date)

        results = query.order_by(MarketPrice.price_date.asc()).all()
        logger.info(f"Found {len(results)} prices for security '{security_id}' with given filters.")
        return results