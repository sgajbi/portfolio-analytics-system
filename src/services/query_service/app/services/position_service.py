# services/query-service/app/services/position_service.py
import logging
from datetime import date
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

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
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PositionRepository(db)

    async def get_position_history(
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
        
        db_results = await self.repo.get_position_history_by_security(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        positions = []
        for row in db_results:
            # FIX: PositionHistory objects do not contain valuation data.
            # The `valuation` field on the DTO is optional and should be None here.
            record = PositionHistoryRecord(
                position_date=row.position_date,
                transaction_id=row.transaction_id,
                quantity=row.quantity,
                cost_basis=row.cost_basis,
                cost_basis_local=row.cost_basis_local,
                valuation=None
            )
            positions.append(record)
        
        return PortfolioPositionHistoryResponse(
            portfolio_id=portfolio_id,
            security_id=security_id,
            positions=positions
        )

    async def get_portfolio_positions(self, portfolio_id: str) -> PortfolioPositionsResponse:
        """
        Retrieves and formats the latest positions for a given portfolio.
        """
        logger.info(f"Fetching latest positions for portfolio '{portfolio_id}'.")
        
        db_results = await self.repo.get_latest_positions_by_portfolio(portfolio_id)
        
        positions = []
        for pos_snapshot, instrument_name in db_results:
            valuation_dto = ValuationData(
                market_price=pos_snapshot.market_price,
                market_value=pos_snapshot.market_value,
                unrealized_gain_loss=pos_snapshot.unrealized_gain_loss,
                market_value_local=pos_snapshot.market_value_local,
                unrealized_gain_loss_local=pos_snapshot.unrealized_gain_loss_local
            )
            position_dto = Position(
                security_id=pos_snapshot.security_id,
                quantity=pos_snapshot.quantity,
                cost_basis=pos_snapshot.cost_basis,
                cost_basis_local=pos_snapshot.cost_basis_local,
                instrument_name=instrument_name or "N/A",
                position_date=pos_snapshot.date,
                valuation=valuation_dto
            )
            positions.append(position_dto)
        
        return PortfolioPositionsResponse(
            portfolio_id=portfolio_id,
            positions=positions
        )