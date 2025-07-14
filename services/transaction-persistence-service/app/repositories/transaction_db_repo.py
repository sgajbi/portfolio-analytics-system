
import logging
from datetime import date # Import date for type conversion
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation # Import the specific psycopg2 error

from common.database_models import Transaction as DBTransaction
from app.models.transaction_event import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_transaction_by_pk(self, transaction_id: str, portfolio_id: str, instrument_id: str, transaction_date: date) -> DBTransaction | None:
        """
        Retrieves a transaction by its primary key components.
        """
        return self.db.query(DBTransaction).filter_by(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            transaction_date=transaction_date
        ).first()

    def create_or_update_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        """
        Attempts to create a transaction. If it exists, it's considered persisted
        and the existing record is returned. This ensures idempotency.
        """
        # 1. Check if the transaction already exists
        existing_transaction = self.get_transaction_by_pk(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            transaction_date=transaction_event.transaction_date # Use the date object directly
        )

        if existing_transaction:
            logger.info(
                f"Transaction {transaction_event.transaction_id} already exists in the database. "
                "Skipping new insertion (idempotent operation)."
            )
            # If you had fields that could update, you would apply them here:
            # existing_transaction.quantity = transaction_event.quantity
            # etc.
            # self.db.commit() # Only commit if updates were made
            return existing_transaction
        else:
            # 2. If it does not exist, attempt to insert
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
            except IntegrityError as e:
                # This block handles potential race conditions (another process inserted it just now)
                if isinstance(e.orig, UniqueViolation):
                    self.db.rollback() # Rollback the failed transaction attempt
                    logger.warning(
                        f"Race condition detected: Transaction {transaction_event.transaction_id} "
                        "was inserted by another process concurrently. Fetching existing record."
                    )
                    # Attempt to fetch the now-existing record
                    return self.get_transaction_by_pk(
                        transaction_id=transaction_event.transaction_id,
                        portfolio_id=transaction_event.portfolio_id,
                        instrument_id=transaction_event.instrument_id,
                        transaction_date=transaction_event.transaction_date
                    )
                raise # Re-raise any other IntegrityErrors that are not UniqueViolation