import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from portfolio_common.database_models import Transaction, Cashflow

logger = logging.getLogger(__name__)

class TransactionRepository:
    """
    Handles read-only database queries for transaction data.
    """
    def __init__(self, db: Session):
        self.db = db

    def _get_base_query(
        self,
        portfolio_id: str,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Session.query:
        """
        Constructs a base query with all the common filters, joining
        transactions with their optional cashflow record.
        """
        query = self.db.query(
            Transaction,
            Cashflow
        ).outerjoin(
            Cashflow, Transaction.transaction_id == Cashflow.transaction_id
        ).filter(
            Transaction.portfolio_id == portfolio_id
        )

        if security_id:
            query = query.filter(Transaction.security_id == security_id)
        if start_date:
            query = query.filter(func.date(Transaction.transaction_date) >= start_date)
        if end_date:
            query = query.filter(func.date(Transaction.transaction_date) <= end_date)
        return query

    def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[tuple]:
        """
        Retrieves a paginated list of transactions with optional filters.
        Returns a list of tuples, where each tuple contains a
        (Transaction, Cashflow | None).
        """
        query = self._get_base_query(portfolio_id, security_id, start_date, end_date)
        results = query.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit).all()
        logger.info(f"Found {len(results)} transactions for portfolio '{portfolio_id}' with given filters.")
        return results

    def get_transactions_count(
        self,
        portfolio_id: str,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> int:
        """
        Returns the total count of transactions for the given filters.
        """
        # For counting, we only need to query the Transaction table.
        query = self.db.query(Transaction).filter(
            Transaction.portfolio_id == portfolio_id
        )
        if security_id:
            query = query.filter(Transaction.security_id == security_id)
        if start_date:
            query = query.filter(func.date(Transaction.transaction_date) >= start_date)
        if end_date:
            query = query.filter(func.date(Transaction.transaction_date) <= end_date)

        count = query.with_entities(func.count(Transaction.id)).scalar()
        return count