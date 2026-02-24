# src/services/query_service/app/services/position_service.py
import logging
from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.position_repository import PositionRepository
from ..dtos.position_dto import (
    Position,
    PortfolioPositionsResponse,
    PositionHistoryRecord,
    PortfolioPositionHistoryResponse,
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
        end_date: Optional[date] = None,
    ) -> PortfolioPositionHistoryResponse:
        """
        Retrieves and formats the position history for a given security.
        """
        logger.info(
            f"Fetching position history for security '{security_id}' in portfolio '{portfolio_id}'."
        )

        db_results = await self.repo.get_position_history_by_security(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )

        positions = []
        for position_history_obj, reprocessing_status in db_results:
            record = PositionHistoryRecord(
                position_date=position_history_obj.position_date,
                transaction_id=position_history_obj.transaction_id,
                quantity=position_history_obj.quantity,
                cost_basis=position_history_obj.cost_basis,
                cost_basis_local=position_history_obj.cost_basis_local,
                valuation=None,
                reprocessing_status=reprocessing_status,
            )
            positions.append(record)

        return PortfolioPositionHistoryResponse(
            portfolio_id=portfolio_id, security_id=security_id, positions=positions
        )

    async def get_portfolio_positions(self, portfolio_id: str) -> PortfolioPositionsResponse:
        """
        Retrieves and formats the latest positions for a given portfolio.
        """
        logger.info(f"Fetching latest positions for portfolio '{portfolio_id}'.")

        db_results = await self.repo.get_latest_positions_by_portfolio(portfolio_id)
        using_snapshot_data = True
        fallback_valuation_map: dict[str, dict[str, float | None]] = {}
        if not db_results:
            db_results = await self.repo.get_latest_position_history_by_portfolio(portfolio_id)
            using_snapshot_data = False
            fallback_valuation_map = await self.repo.get_latest_snapshot_valuation_map(portfolio_id)

        positions = []
        for position_row, instrument, pos_state in db_results:
            valuation_dto = None
            if using_snapshot_data:
                valuation_dto = ValuationData(
                    market_price=position_row.market_price,
                    market_value=position_row.market_value,
                    unrealized_gain_loss=position_row.unrealized_gain_loss,
                    market_value_local=position_row.market_value_local,
                    unrealized_gain_loss_local=position_row.unrealized_gain_loss_local,
                )
            else:
                fallback_valuation = fallback_valuation_map.get(position_row.security_id)
                if fallback_valuation is not None:
                    valuation_dto = ValuationData(
                        market_price=fallback_valuation.get("market_price"),
                        market_value=fallback_valuation.get("market_value"),
                        unrealized_gain_loss=fallback_valuation.get("unrealized_gain_loss"),
                        market_value_local=fallback_valuation.get("market_value_local"),
                        unrealized_gain_loss_local=fallback_valuation.get(
                            "unrealized_gain_loss_local"
                        ),
                    )
                else:
                    # Maintain valuation continuity while snapshot backfill catches up.
                    valuation_dto = ValuationData(
                        market_price=None,
                        market_value=position_row.cost_basis,
                        unrealized_gain_loss=0,
                        market_value_local=position_row.cost_basis_local,
                        unrealized_gain_loss_local=0,
                    )
            position_dto = Position(
                security_id=position_row.security_id,
                quantity=position_row.quantity,
                cost_basis=position_row.cost_basis,
                cost_basis_local=position_row.cost_basis_local,
                instrument_name=instrument.name if instrument else "N/A",
                position_date=(
                    position_row.date if using_snapshot_data else position_row.position_date
                ),
                asset_class=instrument.asset_class if instrument else None,
                valuation=valuation_dto,
                reprocessing_status=pos_state.status if pos_state else None,
            )
            positions.append(position_dto)

        return PortfolioPositionsResponse(portfolio_id=portfolio_id, positions=positions)
