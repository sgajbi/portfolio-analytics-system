import logging
from typing import Optional
from sqlalchemy.orm import Session

from ..repositories.portfolio_repository import PortfolioRepository
from ..dtos.portfolio_dto import PortfolioRecord, PortfolioQueryResponse

logger = logging.getLogger(__name__)

class PortfolioService:
    """
    Handles the business logic for querying portfolio data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = PortfolioRepository(db)

    def get_portfolios(
        self,
        portfolio_id: Optional[str] = None,
        cif_id: Optional[str] = None,
        booking_center: Optional[str] = None
    ) -> PortfolioQueryResponse:
        """
        Retrieves a filtered list of portfolios.
        """
        logger.info(f"Fetching portfolios with filters: portfolio_id={portfolio_id}, cif_id={cif_id}, booking_center={booking_center}")

        # 1. Get the list of portfolio records from the repository
        db_results = self.repo.get_portfolios(
            portfolio_id=portfolio_id,
            cif_id=cif_id,
            booking_center=booking_center
        )

        # 2. Map the database results to our DTO
        portfolios = [PortfolioRecord.model_validate(row) for row in db_results]

        # 3. Construct the final API response object
        return PortfolioQueryResponse(portfolios=portfolios)