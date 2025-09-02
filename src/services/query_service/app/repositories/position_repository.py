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
        # This CTE finds the most recent date the position quantity was zero or non-existent.
        # It acts as a "break point" in the holding history.
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

        # This query finds the date of the first transaction *after* that last zero point.
        # If no zero point exists, it finds the overall first transaction date.
        stmt = (
            select(func.min(PositionHistory.position_date))
            .select_from(PositionHistory)
            .join(last_zero_date_cte, text("1=1"), isouter=True) # Cross join or outer join to ensure it's available
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
            PositionState.epoch,
            Instrument.name.label("instrument_name"),
            Instrument.isin,
            Instrument.currency,
            Instrument.asset_class,
            Instrument.sector,
            Instrument.country_of_risk,
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
            ranked_snapshots_subq.c.isin,
            ranked_snapshots_subq.c.currency,
            ranked_snapshots_subq.c.asset_class,
            ranked_snapshots_subq.c.sector,
            ranked_snapshots_subq.c.country_of_risk,
            ranked_snapshots_subq.c.issuer_id,
            ranked_snapshots_subq.c.ultimate_parent_issuer_id,
            ranked_snapshots_subq.c.epoch
        ).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_alias.quantity > 0
        )
        
        results = await self.db.execute(stmt)
        positions = results.all()
        logger.info(f"Found {len(positions)} latest positions for portfolio '{portfolio_id}'.")
        return positions