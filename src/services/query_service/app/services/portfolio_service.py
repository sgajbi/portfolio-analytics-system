# services/query-service/app/services/portfolio_service.py
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.portfolio_dto import PortfolioRecord, PortfolioQueryResponse
from portfolio_common.database_models import Portfolio

logger = logging.getLogger(__name__)

class PortfolioService:
    """
    Handles the business logic for querying portfolio data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PortfolioRepository(db)

    async def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        cif_id: Optional[str] = None,
        booking_center: Optional[str] = None
    ) -> PortfolioQueryResponse:
        """
        Retrieves a filtered list of portfolios.
        """
        logger.info(f"Fetching portfolios with filters: portfolio_id={portfolio_id}, cif_id={cif_id}, booking_center={booking_center}")

        db_results = await self.repo.get_portfolios(
            portfolio_id=portfolio_id,
            cif_id=cif_id,
            booking_center=booking_center
        )

        portfolios = [PortfolioRecord.model_validate(p) for p in db_results]

        return PortfolioQueryResponse(portfolios=portfolios)

    async def get_portfolio_by_id(self, portfolio_id: str) -> Portfolio:
        """
        Retrieves a single portfolio by its ID.
        Raises an exception if the portfolio is not found.
        """
        logger.info(f"Fetching portfolio with id: {portfolio_id}")
        db_portfolio = await self.repo.get_by_id(portfolio_id)
        if not db_portfolio:
            raise ValueError(f"Portfolio with id {portfolio_id} not found")
        return db_portfolio