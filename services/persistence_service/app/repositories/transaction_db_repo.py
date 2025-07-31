# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates a new transaction. If a transaction with the same
        transaction_id already exists, it is returned without making changes.
        
        Note: This method does NOT commit the session. The caller is responsible
        for transaction management.
        """
        # 1. Check for existence using the correct unique key.
        existing_transaction = self.db.query(DBTransaction).filter_by(
            transaction_id=transaction_event.transaction_id
        ).first()

        if existing_transaction:
            logger.info(f"Transaction {transaction_event.transaction_id} already exists. Skipping.")
            return existing_transaction
        
        # 2. If it doesn't exist, create and add the new object to the session.
        db_transaction = DBTransaction(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            security_id=transaction_event.security_id,
            transaction_date=transaction_event.transaction_date,
            transaction_type=transaction_event.transaction_type,
            quantity=transaction_event.quantity,
            price=transaction_event.price,
            gross_transaction_amount=transaction_event.gross_transaction_amount,
            trade_currency=transaction_event.trade_currency,
            currency=transaction_event.currency,
            trade_fee=transaction_event.trade_fee,
            settlement_date=transaction_event.settlement_date
        )
        
        self.db.add(db_transaction)
        logger.info(f"Transaction {db_transaction.transaction_id} staged for insertion.")
        return db_transaction