# src/services/query_service/app/repositories/summary_repository.py
import logging
from datetime import date
from typing import List, Any, Dict
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from portfolio_common.database_models import DailyPositionSnapshot, PositionState, Instrument, Cashflow, Transaction
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
        """
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

        ranked_alias = aliased(DailyPositionSnapshot, ranked_snapshots_subq)
        instrument_alias = aliased(Instrument, ranked_snapshots_subq)

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

    @async_timed(repository="SummaryRepository", method="get_cashflows_for_period")
    async def get_cashflows_for_period(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> List[Cashflow]:
        """
        Fetches all cashflow records for the specified period, filtered by the current epoch.
        """
        current_epoch_subq = (
            select(func.max(PositionState.epoch))
            .where(PositionState.portfolio_id == portfolio_id)
            .scalar_subquery()
        )

        stmt = (
            select(Cashflow)
            .join(PositionState, (PositionState.portfolio_id == Cashflow.portfolio_id))
            .where(
                Cashflow.portfolio_id == portfolio_id,
                Cashflow.cashflow_date.between(start_date, end_date),
                Cashflow.epoch == func.coalesce(current_epoch_subq, 0)
            )
            .order_by(Cashflow.cashflow_date)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    @async_timed(repository="SummaryRepository", method="get_realized_pnl")
    async def get_realized_pnl(self, portfolio_id: str, start_date: date, end_date: date) -> Decimal:
        """
        Calculates the total realized P&L for a portfolio over a given period.
        """
        stmt = (
            select(func.sum(Transaction.realized_gain_loss))
            .where(
                Transaction.portfolio_id == portfolio_id,
                func.date(Transaction.transaction_date).between(start_date, end_date),
                Transaction.realized_gain_loss.is_not(None)
            )
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or Decimal(0)

    @async_timed(repository="SummaryRepository", method="get_total_unrealized_pnl")
    async def get_total_unrealized_pnl(self, portfolio_id: str, as_of_date: date) -> Decimal:
        """
        Calculates the total unrealized P&L for all positions in a portfolio
        on a given date, based on the latest snapshots for the current epoch.
        """
        ranked_snapshots_subq = select(
            DailyPositionSnapshot.unrealized_gain_loss,
            DailyPositionSnapshot.quantity,
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
        ).filter(
            DailyPositionSnapshot.portfolio_id == portfolio_id,
            DailyPositionSnapshot.date <= as_of_date
        ).subquery('ranked_snapshots')

        stmt = select(func.sum(ranked_snapshots_subq.c.unrealized_gain_loss)).filter(
            ranked_snapshots_subq.c.rn == 1,
            ranked_snapshots_subq.c.quantity > 0
        )
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() or Decimal(0)