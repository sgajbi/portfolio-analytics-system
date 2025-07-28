import logging
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session

from ..repositories.position_repository import PositionRepository
from ..dtos.position_dto import (
    Position, 
    PortfolioPositionsResponse,
    PositionHistoryRecord,
    PortfolioPositionHistoryResponse
)
from ..dtos.valuation_dto import ValuationData

logger = logging.getLogger(__name__)

class PositionService:
    """
    Handles the business logic for querying position data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = PositionRepository(db)

    def get_position_history(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> PortfolioPositionHistoryResponse:
        """
        Retrieves and formats the position history for a given security.
        """
        logger.info(f"Fetching position history for security '{security_id}' in portfolio '{portfolio_id}'.")
        
        # 1. Get raw history data from the repository
        db_results = self.repo.get_position_history_by_security(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Map the database results to our PositionHistoryRecord DTO with nested valuation
        positions = []
        for row in db_results:
            valuation_data = ValuationData.model_validate(row)
            record = PositionHistoryRecord.model_validate(row)
            record.valuation = valuation_data
            positions.append(record)
        
        # 3. Construct the final API response object
        return PortfolioPositionHistoryResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            positions=positions
        )

    def get_portfolio_positions(self, portfolio_id: str) -> PortfolioPositionsResponse:
        """
        Retrieves and formats the latest positions for a given portfolio.
        """
        logger.info(f"Fetching latest positions for portfolio '{portfolio_id}'.")
        
        db_results = self.repo.get_latest_positions_by_portfolio(portfolio_id)
        
        # Map the (PositionHistory, instrument_name) tuples to the Position DTO
        positions = []
        for pos_history, instrument_name in db_results:
            valuation_data = ValuationData.model_validate(pos_history)
            
            # Manually construct the dictionary for the Position DTO
            position_data = {
                "security_id": pos_history.security_id,
                "quantity": pos_history.quantity,
                "cost_basis": pos_history.cost_basis,
                "instrument_name": instrument_name or "N/A",
                "position_date": pos_history.position_date,
                "valuation": valuation_data
            }
            positions.append(Position.model_validate(position_data))
        
        return PortfolioPositionsResponse(
            portfolio_id=portfolio_id,
            positions=positions
        )