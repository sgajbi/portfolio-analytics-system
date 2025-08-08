# services/query-service/app/repositories/transaction_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from portfolio_common.database_models import Transaction, Cashflow
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

class TransactionRepository:
    """
    Handles read-only database queries for transaction data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_base_query(
        self,
        portfolio_id: str,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ):
        """
        Constructs a base query with all the common filters.
        """
        stmt = select(Transaction).options(selectinload(Transaction.cashflow)).filter_by(portfolio_id=portfolio_id)

        if security_id:
            stmt = stmt.filter_by(security_id=security_id)
        if start_date:
            stmt = stmt.filter(func.date(Transaction.transaction_date) >= start_date)
        if end_date:
            stmt = stmt.filter(func.date(Transaction.transaction_date) <= end_date)
        return stmt

    @async_timed(repository="TransactionRepository", method="get_transactions")
    async def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Transaction]:
        """
        Retrieves a paginated list of transactions with optional filters.
        """
        stmt = self._get_base_query(portfolio_id, security_id, start_date, end_date)
        results = await self.db.execute(stmt.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit))
        transactions = results.scalars().all()
        logger.info(f"Found {len(transactions)} transactions for portfolio '{portfolio_id}' with given filters.")
        return transactions

    @async_timed(repository="TransactionRepository", method="get_transactions_count")
    async def get_transactions_count(
        self,
        portfolio_id: str,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> int:
        """
        Returns the total count of transactions for the given filters.
        """
        stmt = select(func.count(Transaction.id)).filter_by(portfolio_id=portfolio_id)
        if security_id:
            stmt = stmt.filter_by(security_id=security_id)
        if start_date:
            stmt = stmt.filter(func.date(Transaction.transaction_date) >= start_date)
        if end_date:
            stmt = stmt.filter(func.date(Transaction.transaction_date) <= end_date)

        count = (await self.db.execute(stmt)).scalar()
        return count