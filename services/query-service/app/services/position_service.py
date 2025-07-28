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
        
        db_results = self.repo.get_position_history_by_security(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        positions = []
        for row in db_results:
            # Explicitly create the nested valuation object
            valuation_dto = ValuationData(
                market_price=row.market_price,
                market_value=row.market_value,
                unrealized_gain_loss=row.unrealized_gain_loss,
            )
            # Create the main record and attach the valuation object
            record = PositionHistoryRecord(
                position_date=row.position_date,
                transaction_id=row.transaction_id,
                quantity=row.quantity,
                cost_basis=row.cost_basis,
                valuation=valuation_dto
            )
            positions.append(record)
        
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
        
        positions = []
        for pos_history, instrument_name in db_results:
            # Explicitly create the nested valuation object
            valuation_dto = ValuationData(
                market_price=pos_history.market_price,
                market_value=pos_history.market_value,
                unrealized_gain_loss=pos_history.unrealized_gain_loss,
            )
            # Create the main position object
            position_dto = Position(
                security_id=pos_history.security_id,
                quantity=pos_history.quantity,
                cost_basis=pos_history.cost_basis,
                instrument_name=instrument_name or "N/A",
                position_date=pos_history.position_date,
                valuation=valuation_dto
            )
            positions.append(position_dto)
        
        return PortfolioPositionsResponse(
            portfolio_id=portfolio_id,
            positions=positions
        )