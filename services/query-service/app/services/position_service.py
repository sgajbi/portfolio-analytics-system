import logging
from typing import List
from sqlalchemy.orm import Session

from ..repositories.position_repository import PositionRepository
from ..dtos.position_dto import Position, PortfolioPositionsResponse

logger = logging.getLogger(__name__)

class PositionService:
    """
    Handles the business logic for querying position data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = PositionRepository(db)

    def get_portfolio_positions(self, portfolio_id: str) -> PortfolioPositionsResponse:
        """
        Retrieves and formats the latest positions for a given portfolio.
        """
        logger.info(f"Fetching latest positions for portfolio '{portfolio_id}'.")
        
        # 1. Get raw position data from the repository
        db_results = self.repo.get_latest_positions_by_portfolio(portfolio_id)
        
        # 2. Map the database results to our Position DTO
        positions = [Position.model_validate(row) for row in db_results]
        
        # 3. Construct the final API response object
        return PortfolioPositionsResponse(
            portfolio_id=portfolio_id,
            positions=positions
        )