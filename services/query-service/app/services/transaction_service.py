# services/query-service/app/services/transaction_service.py
import logging
from datetime import date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.transaction_repository import TransactionRepository
from ..dtos.transaction_dto import TransactionRecord, PaginatedTransactionResponse

logger = logging.getLogger(__name__)

class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TransactionRepository(db)

    async def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        sort_by: Optional[str] = None,      # <-- ADD PARAMETER
        sort_order: Optional[str] = "desc", # <-- ADD PARAMETER
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> PaginatedTransactionResponse:
        """
        Retrieves a paginated and filtered list of transactions for a portfolio.
        """
        logger.info(f"Fetching transactions for portfolio '{portfolio_id}'.")
        
        total_count = await self.repo.get_transactions_count(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )

        db_results = await self.repo.get_transactions(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        transactions = []
        for transaction in db_results:
            record = TransactionRecord.model_validate(transaction)
            if transaction.cashflow:
                record.cashflow = transaction.cashflow
            transactions.append(record)

        return PaginatedTransactionResponse(
            portfolio_id=portfolio_id,
            total=total_count,
            skip=skip,
            limit=limit,
            transactions=transactions
        )