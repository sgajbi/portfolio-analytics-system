# services/query-service/app/repositories/transaction_repository.py
import logging
from datetime import date
from typing import List, Optional

from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from portfolio_common.database_models import Transaction
from portfolio_common.utils import async_timed

logger = logging.getLogger(__name__)

# Whitelist of columns that clients are allowed to sort by.
ALLOWED_SORT_FIELDS = {"transaction_date", "quantity", "price", "gross_transaction_amount"}


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
        end_date: Optional[date] = None,
    ):
        """
        Constructs a base query with all the common filters.
        """
        # FIX: Change from selectinload to joinedload for reliable eager loading
        stmt = (
            select(Transaction)
            .options(joinedload(Transaction.cashflow))
            .filter_by(portfolio_id=portfolio_id)
        )

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
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = "desc",
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Transaction]:
        """
        Retrieves a paginated list of transactions with optional filters.
        """
        stmt = self._get_base_query(portfolio_id, security_id, start_date, end_date)

        sort_field = "transaction_date"
        if sort_by and sort_by in ALLOWED_SORT_FIELDS:
            sort_field = sort_by

        normalized_sort_order = (sort_order or "desc").lower()
        sort_direction = asc if normalized_sort_order == "asc" else desc
        order_clause = sort_direction(getattr(Transaction, sort_field))

        stmt = stmt.order_by(order_clause)

        results = await self.db.execute(stmt.offset(skip).limit(limit))
        transactions = results.scalars().unique().all()
        logger.info(
            f"Found {len(transactions)} transactions for portfolio '{portfolio_id}' with given filters."
        )
        return transactions

    @async_timed(repository="TransactionRepository", method="get_transactions_count")
    async def get_transactions_count(
        self,
        portfolio_id: str,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
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

        count = (await self.db.execute(stmt)).scalar() or 0
        return count
