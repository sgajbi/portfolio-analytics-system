# src/services/query_service/app/repositories/cashflow_repository.py
import logging
from datetime import date
from typing import List, Tuple
from decimal import Decimal

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Cashflow, PositionState
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class CashflowRepository:
    """
    Handles read-only database queries for cashflow data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    @async_timed(repository="CashflowRepository", method="get_external_flows")
    async def get_external_flows(
        self, portfolio_id: str, start_date: date, end_date: date
    ) -> List[Tuple[date, Decimal]]:
        """
        Fetches only the external investor cashflows for a portfolio within a date range.
        These are used for MWR (IRR) calculations.
        """
        stmt = (
            select(Cashflow.cashflow_date, Cashflow.amount)
            .where(
                Cashflow.portfolio_id == portfolio_id,
                Cashflow.cashflow_date.between(start_date, end_date),
                Cashflow.is_portfolio_flow == True,
                Cashflow.classification.in_(['CASHFLOW_IN', 'CASHFLOW_OUT'])
            )
            .order_by(Cashflow.cashflow_date.asc())
        )
        result = await self.db.execute(stmt)
        return result.all()

    @async_timed(repository="CashflowRepository", method="get_income_cashflows_for_position")
    async def get_income_cashflows_for_position(
        self, portfolio_id: str, security_id: str, start_date: date, end_date: date
    ) -> List[Cashflow]:
        """
        Retrieves all income-classified cashflow records for a single position
        within a date range, ensuring data is from the correct epoch.
        """
        stmt = (
            select(Cashflow)
            .join(
                PositionState,
                and_(
                    PositionState.portfolio_id == Cashflow.portfolio_id,
                    PositionState.security_id == Cashflow.security_id,
                    PositionState.epoch == Cashflow.epoch
                )
            )
            .where(
                Cashflow.portfolio_id == portfolio_id,
                Cashflow.security_id == security_id,
                Cashflow.cashflow_date.between(start_date, end_date),
                Cashflow.classification == 'INCOME'
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()