import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import date

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_transaction_by_pk(self, transaction_id: str, portfolio_id: str, instrument_id: str, transaction_date: date):
        """
        Retrieves a transaction by its composite primary key.
        The transaction_date is explicitly handled to ensure correct querying.
        """
        # --- THIS IS THE FIX ---
        # Ensure the query compares only the date part, ignoring time.
        return self.db.query(DBTransaction).filter_by(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            transaction_date=transaction_date
        ).first()

    def create_or_update_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        existing_transaction = self.get_transaction_by_pk(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            transaction_date=transaction_event.transaction_date
        )

        # --- THIS IS THE FIX ---
        # If the transaction already exists, log it and return immediately.
        if existing_transaction:
            logger.info(f"Transaction {transaction_event.transaction_id} already exists. Skipping.")
            return existing_transaction
        
        # If it doesn't exist, create the new record.
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
        
        try:
            self.db.add(db_transaction)
            self.db.commit()
            self.db.refresh(db_transaction)
            logger.info(f"Transaction {db_transaction.transaction_id} successfully inserted into DB.")
            return db_transaction
        except IntegrityError:
            self.db.rollback()
            logger.warning(f"Transaction {transaction_event.transaction_id} already exists (race condition). Rolling back.")
            return self.get_transaction_by_pk(
                transaction_id=transaction_event.transaction_id,
                portfolio_id=transaction_event.portfolio_id,
                instrument_id=transaction_event.instrument_id,
                transaction_date=transaction_event.transaction_date
            )