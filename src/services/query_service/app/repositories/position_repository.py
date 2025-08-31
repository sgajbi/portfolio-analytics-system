# src/services/query_service/app/repositories/position_repository.py
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
    ) -> List[Any]: # UPDATED: Return type is now a list of rows/tuples
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
        history = results.all() # UPDATED: Use .all() to get rows
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
        # Subquery to rank snapshots within each security, but only for snapshots
        # that match the current epoch defined in the position_state table.
        ranked_snapshots_subq = select(
            DailyPositionSnapshot,
            Instrument.name.label("instrument_name"),
            Instrument.asset_class,
            Instrument.issuer_id,
            Instrument.ultimate_parent_issuer_id,
            PositionState.status.label("reprocessing_status"),
            func.row_number().over(
                partition_by=DailyPositionSnapshot.security_id,
                order_by=[
                    DailyPositionSnapshot.date.desc(),
                    DailyPositionSnapshot.id.desc()
                ]
            ).label('rn')
        ).join(
            PositionState,
            (DailyPositionSnapshot.portfolio_id == PositionState.portfolio_id) &
            (DailyPositionSnapshot.security_id == PositionState.security_id) &
            (DailyPositionSnapshot.epoch == PositionState.epoch)
        ).join(
            Instrument, Instrument.security_id == DailyPositionSnapshot.security_id, isouter=True
        ).filter(
            DailyPositionSnapshot.portfolio_id == portfolio_id
        ).subquery('ranked_snapshots')

        ranked_alias = aliased(DailyPositionSnapshot, ranked_snapshots_subq)

        # Final query to select the top-ranked snapshot (rn=1) for each security
        # and filter out any closed positions (quantity > 0).
        stmt = select(
            ranked_alias,
            ranked_snapshots_subq.c.instrument_name,
            ranked_snapshots_subq.c.reprocessing_status,
            ranked_snapshots_subq.c.asset_class,
            ranked_snapshots_subq.c.issuer_id,
            ranked_snapshots_subq.c.ultimate_parent_issuer_id
        ).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_alias.quantity > 0
        )
        
        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(f"Found {len(positions)} latest positions for portfolio '{portfolio_id}'.")
        return positions