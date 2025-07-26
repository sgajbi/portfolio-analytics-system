import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from portfolio_common.database_models import FxRate

logger = logging.getLogger(__name__)

class FxRateRepository:
    """
    Handles read-only database queries for FX rate data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_fx_rates(
        self,
        from_currency: str,
        to_currency: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[FxRate]:
        """
        Retrieves a list of FX rates for a currency pair, with optional
        date range filtering.
        """
        query = self.db.query(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency
        )

        if start_date:
            query = query.filter(FxRate.rate_date >= start_date)
        
        if end_date:
            query = query.filter(FxRate.rate_date <= end_date)

        results = query.order_by(FxRate.rate_date.asc()).all()
        logger.info(f"Found {len(results)} FX rates for '{from_currency}-{to_currency}' with given filters.")
        return results