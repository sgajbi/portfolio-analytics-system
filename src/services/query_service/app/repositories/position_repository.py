# services/query-service/app/repositories/position_repository.py
import logging
from datetime import date
from typing import List, Any, Optional

from sqlalchemy import select, func
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

    async def get_position_history_by_security(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[PositionHistory]:
        """
        Retrieves the time series of position history for a specific security,
        filtered to include only records from the current epoch for that key.
        """
        stmt = (
            select(PositionHistory)
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
        history = results.scalars().all()
        logger.info(
            f"Found {len(history)} position history records for security '{security_id}' "
            f"in portfolio '{portfolio_id}'."
        )
        return history

    async def get_latest_positions_by_portfolio(self, portfolio_id: str) -> List[Any]:
        """
        Retrieves the single latest daily snapshot for each security in a given portfolio,
        ensuring that the snapshot belongs to the current epoch for that security.
        """
        # Subquery to get the latest epoch for each security in the portfolio
        latest_epoch_subq = (
            select(
                PositionState.security_id,
                func.max(PositionState.epoch).label("max_epoch")
            )
            .where(PositionState.portfolio_id == portfolio_id)
            .group_by(PositionState.security_id)
            .subquery('latest_epoch')
        )

        # Subquery to rank snapshots within each security's latest epoch
        ranked_snapshots_subq = select(
            DailyPositionSnapshot,
            func.row_number().over(
                partition_by=DailyPositionSnapshot.security_id,
                order_by=[
                    DailyPositionSnapshot.date.desc(),
                    DailyPositionSnapshot.id.desc()
                ]
            ).label('rn')
        ).join(
            latest_epoch_subq,
            (DailyPositionSnapshot.security_id == latest_epoch_subq.c.security_id) &
            (DailyPositionSnapshot.epoch == latest_epoch_subq.c.max_epoch)
        ).filter(
            DailyPositionSnapshot.portfolio_id == portfolio_id
        ).subquery('ranked_snapshots')

        ranked_alias = aliased(DailyPositionSnapshot, ranked_snapshots_subq)

        # Final query to select the top-ranked snapshot for each security
        stmt = select(
            ranked_alias,
            Instrument.name.label('instrument_name')
        ).join(
            Instrument, Instrument.security_id == ranked_alias.security_id, isouter=True
        ).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_alias.quantity > 0
        )

        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(f"Found {len(positions)} latest positions for portfolio '{portfolio_id}'.")
        return positions