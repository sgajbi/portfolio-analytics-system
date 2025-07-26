import logging
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session

from ..repositories.transaction_repository import TransactionRepository
from ..dtos.transaction_dto import TransactionRecord, PaginatedTransactionResponse

logger = logging.getLogger(__name__)

class TransactionService:
    """
    Handles the business logic for querying transaction data.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionRepository(db)

    def get_transactions(
        self,
        portfolio_id: str,
        skip: int,
        limit: int,
        security_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> PaginatedTransactionResponse:
        """
        Retrieves a paginated and filtered list of transactions for a portfolio.
        """
        logger.info(f"Fetching transactions for portfolio '{portfolio_id}'.")
        
        # 1. Get the total count for pagination metadata
        total_count = self.repo.get_transactions_count(
            portfolio_id=portfolio_id,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )

        # 2. Get the paginated list of transactions
        db_results = self.repo.get_transactions(
            portfolio_id=portfolio_id,
            skip=skip,
            limit=limit,
            security_id=security_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # 3. Map the database results to our TransactionRecord DTO
        transactions = [TransactionRecord.model_validate(row) for row in db_results]
        
        # 4. Construct the final API response object
        return PaginatedTransactionResponse(
            portfolio_id=portfolio_id,
            total=total_count,
            skip=skip,
            limit=limit,
            transactions=transactions
        )