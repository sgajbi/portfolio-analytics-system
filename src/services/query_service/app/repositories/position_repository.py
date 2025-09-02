# src/services/query_service/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Any, Optional

from sqlalchemy import select, func, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Instrument, DailyPositionSnapshot, PositionState

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles read-only database queries for position data, ensuring that
    only data from the latest completed epoch is returned.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_held_since_date(self, portfolio_id: str, security_id: str, epoch: int) -> Optional[date]:
        """
        Finds the 'held since date' for a position in a given epoch.
        This is the start of the current continuous holding period.
        """

        last_zero_date_cte = (
            select(
                func.max(PositionHistory.position_date).label("last_zero_date")
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == epoch,
                PositionHistory.quantity == 0
            )
            .cte("last_zero_date")
        )

        stmt = (
            select(func.min(PositionHistory.position_date))
            .select_from(PositionHistory)
            .join(last_zero_date_cte, text("1=1"), isouter=True) 
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == epoch,
                PositionHistory.position_date > func.coalesce(last_zero_date_cte.c.last_zero_date, date.min)
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


    async def get_position_history_by_security(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Any]: 
        """
        Retrieves the time series of position history for a specific security,
        filtered to include only records from the current epoch for that key.
        """
        stmt = (
            select(
                PositionHistory,
                PositionState.status.label("reprocessing_status")
            )
            .join(
                PositionState,
                (PositionHistory.portfolio_id == PositionState.portfolio_id) &
                (PositionHistory.security_id == PositionState.security_id)
            )
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.epoch == PositionState.epoch
            )
        )

        if start_date:
            stmt = stmt.filter(PositionHistory.position_date >= start_date)
        
        if end_date:
            stmt = stmt.filter(PositionHistory.position_date <= end_date)

        results = await self.db.execute(stmt.order_by(PositionHistory.position_date.asc()))
        history = results.all()
        logger.info(
            f"Found {len(history)} position history records for security '{security_id}' "
            f"in portfolio '{portfolio_id}'."
        )
        return history

    async def get_latest_positions_by_portfolio(self, portfolio_id: str) -> List[Any]:
        """
        Retrieves the single latest daily snapshot for each security in a given portfolio,
        ensuring that the snapshot belongs to the current epoch for that security.
        It eagerly loads the related Instrument and PositionState data.
        """
        latest_snapshot_subq = (
            select(func.max(DailyPositionSnapshot.id).label("max_id"))
            .join(
                PositionState,
                (DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id) &
                (DailyPositionSnapshot.security_id == PositionState.security_id) &
                (DailyPositionSnapshot.epoch == PositionState.epoch)
            )
            .filter(
                DailyPositionSnapshot.portfolio_id == portfolio_id
            )
            .group_by(DailyPositionSnapshot.security_id)
            .subquery()
        )

        stmt = (
            select(DailyPositionSnapshot, Instrument, PositionState)
            .join(latest_snapshot_subq, DailyPositionSnapshot.id == latest_snapshot_subq.c.max_id)
            .join(Instrument, Instrument.security_id == DailyPositionSnapshot.security_id)
            .join(PositionState,
                  (PositionState.portfolio_id == DailyPositionSnapshot.portfolio_id) &
                  (PositionState.security_id == DailyPositionSnapshot.security_id) &
                  (PositionState.epoch == DailyPositionSnapshot.epoch))
            .filter(DailyPositionSnapshot.quantity > 0)
        )
        
        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(f"Found {len(positions)} latest positions for portfolio '{portfolio_id}'.")
        return positions