from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from common.models import Transaction, TransactionCost
from common.db import SessionLocal
from datetime import date, datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class TransactionRepository:
    """
    Repository class for handling database operations related to Transactions and TransactionCosts.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_transaction_by_pk(
        self,
        transaction_id: str,
        portfolio_id: str,
        instrument_id: str,
        transaction_date: date
    ) -> Optional[Transaction]:
        """
        Retrieves a single transaction by its composite primary key.
        """
        return self.db.query(Transaction).filter(
            Transaction.transaction_id == transaction_id,
            Transaction.portfolio_id == portfolio_id,
            Transaction.instrument_id == instrument_id,
            Transaction.transaction_date == transaction_date
        ).first()

    def create_transaction_cost(
        self,
        transaction_cost: TransactionCost
    ) -> TransactionCost:
        """
        Creates a new transaction cost record in the database.
        """
        try:
            self.db.add(transaction_cost)
            self.db.commit()
            self.db.refresh(transaction_cost)
            return transaction_cost
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Error creating transaction cost: {e}")
            raise # Re-raise the exception after rollback