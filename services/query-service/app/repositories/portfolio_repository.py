import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from portfolio_common.database_models import Portfolio

logger = logging.getLogger(__name__)

class PortfolioRepository:
    """
    Handles read-only database queries for portfolio data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        cif_id: Optional[str] = None,
        booking_center: Optional[str] = None
    ) -> List[Portfolio]:
        """
        Retrieves a list of portfolios with optional filters.
        """
        query = self.db.query(Portfolio)

        if portfolio_id:
            query = query.filter(Portfolio.portfolio_id == portfolio_id)

        if cif_id:
            query = query.filter(Portfolio.cif_id == cif_id)

        if booking_center:
            query = query.filter(Portfolio.booking_center == booking_center)

        results = query.order_by(Portfolio.portfolio_id.asc()).all()
        logger.info(f"Found {len(results)} portfolios with the given filters.")
        return results