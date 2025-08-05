# services/query-service/app/repositories/portfolio_repository.py
import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Portfolio

logger = logging.getLogger(__name__)

class PortfolioRepository:
    """
    Handles read-only database queries for portfolio data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        cif_id: Optional[str] = None,
        booking_center: Optional[str] = None
    ) -> List[Portfolio]:
        """
        Retrieves a list of portfolios with optional filters.
        """
        stmt = select(Portfolio)

        if portfolio_id:
            stmt = stmt.filter_by(portfolio_id=portfolio_id)

        if cif_id:
            stmt = stmt.filter_by(cif_id=cif_id)

        if booking_center:
            stmt = stmt.filter_by(booking_center=booking_center)

        results = await self.db.execute(stmt.order_by(Portfolio.portfolio_id.asc()))
        portfolios = results.scalars().all()
        logger.info(f"Found {len(portfolios)} portfolios with the given filters.")
        return portfolios