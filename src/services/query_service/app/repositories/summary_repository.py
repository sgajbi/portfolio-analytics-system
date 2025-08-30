# src/services/query_service/app/repositories/summary_repository.py
import logging
from datetime import date
from typing import List, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from portfolio_common.database_models import DailyPositionSnapshot, PositionState, Instrument
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class SummaryRepository:
    """
    Handles read-only database queries for the portfolio summary endpoint.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="SummaryRepository", method="get_wealth_and_allocation_data")
    async def get_wealth_and_allocation_data(self, portfolio_id: str, as_of_date: date) -> List[Any]:
        """
        Retrieves the single latest daily snapshot for each security in a given portfolio
        on or before the as_of_date, ensuring the snapshot belongs to the current epoch.
        The result is joined with instrument data for allocation calculations.

        Returns a list of Row objects, each containing a DailyPositionSnapshot and its
        corresponding Instrument.
        """
        # Subquery to rank snapshots within each security, but only for snapshots
        # that match the current epoch defined in the position_state table.
        ranked_snapshots_subq = select(
            DailyPositionSnapshot,
            Instrument,
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
            Instrument, Instrument.security_id == DailyPositionSnapshot.security_id
        ).filter(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.date <= as_of_date
        ).subquery('ranked_snapshots')

        # Use an alias to query from the subquery
        ranked_alias = aliased(DailyPositionSnapshot, ranked_snapshots_subq)
        instrument_alias = aliased(Instrument, ranked_snapshots_subq)

        # Final query to select the top-ranked snapshot (rn=1) for each security
        # and filter out any closed positions (quantity > 0).
        stmt = select(
            ranked_alias,
            instrument_alias
        ).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_alias.quantity > 0
        )
        
        results = await self.db.execute(stmt)
        data = results.all()
        logger.info(f"Found {len(data)} open positions for portfolio '{portfolio_id}' for summary as of {as_of_date}.")
        return data