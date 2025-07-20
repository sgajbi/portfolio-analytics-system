import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from common.database_models import Transaction as DBTransaction
from common.events import TransactionEvent # <-- THE FIX: Import from common/events.py

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_transaction_by_pk(
        self,
        transaction_id: str,
        portfolio_id: str,
        instrument_id: str,
        transaction_date: str
    ):
        """Retrieves a transaction by its primary key components."""
        return self.db.query(DBTransaction).filter_by(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            transaction_date=transaction_date
        ).first()

    def create_or_update_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        """
        Creates a transaction if it does not exist, ensuring idempotency.
        """
        existing_transaction = self.get_transaction_by_pk(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            transaction_date=transaction_event.transaction_date
        )

        if existing_transaction:
            logger.info(f"Transaction {transaction_event.transaction_id} already exists. Skipping.")
            return existing_transaction
        else:
            try:
                db_transaction = DBTransaction(
                    transaction_id=transaction_event.transaction_id,
                    portfolio_id=transaction_event.portfolio_id,
                    instrument_id=transaction_event.instrument_id,
                    transaction_date=transaction_event.transaction_date,
                    transaction_type=transaction_event.transaction_type,
                    quantity=transaction_event.quantity,
                    price=transaction_event.price,
                    currency=transaction_event.currency,
                    trade_fee=transaction_event.trade_fee,
                    settlement_date=transaction_event.settlement_date,
                )
                self.db.add(db_transaction)
                self.db.commit()
                self.db.refresh(db_transaction)
                logger.info(f"Transaction {db_transaction.transaction_id} successfully inserted into DB.")
                return db_transaction
            except IntegrityError:
                self.db.rollback()
                logger.warning(f"Race condition for {transaction_event.transaction_id}. Fetching existing.")
                return self.get_transaction_by_pk(
                    transaction_id=transaction_event.transaction_id,
                    portfolio_id=transaction_event.portfolio_id,
                    instrument_id=transaction_event.instrument_id,
                    transaction_date=transaction_event.transaction_date
                )