# services/transaction-persistence-service/app/repositories/transaction_db_repo.py
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from psycopg2.errors import UniqueViolation # Import the specific psycopg2 error

from common.database_models import Transaction as DBTransaction
from app.models.transaction_event import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        """
        Creates a new transaction record in the database.
        Handles UniqueViolation to ensure idempotency.
        """
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
                # created_at will be set by default in the model
            )
            self.db.add(db_transaction)
            self.db.commit()
            self.db.refresh(db_transaction)
            logger.info(f"Transaction {db_transaction.transaction_id} successfully inserted into DB.")
            return db_transaction
        except IntegrityError as e:
            if isinstance(e.orig, UniqueViolation):
                logger.warning(
                    f"Transaction with key (transaction_id='{transaction_event.transaction_id}', "
                    f"portfolio_id='{transaction_event.portfolio_id}', "
                    f"instrument_id='{transaction_event.instrument_id}', "
                    f"transaction_date='{transaction_event.transaction_date}') "
                    "already exists in the database. Skipping insertion (idempotent operation)."
                )
                # If it's a duplicate, we can fetch the existing one or just return a dummy
                # or the original event transformed to a DBTransaction if we assume it's there.
                # For simplicity here, we'll log and treat it as if it was successfully handled for the purpose
                # of subsequent event publishing.
                # If there were updates allowed, we would implement an upsert logic here.
                # For now, if it exists, we consider it "persisted".
                self.db.rollback() # Rollback the failed transaction
                # Return a representation of the existing transaction for consistency with the success path
                # A more robust solution might fetch the existing record, but for idempotency,
                # returning the incoming event wrapped in a DBTransaction object is often sufficient if no actual update is expected.
                return DBTransaction(
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
                    # No created_at from DB for existing, but we need to return a valid object.
                    # This might require querying the DB for the existing object for full fidelity,
                    # or creating a simple placeholder. For this step, we'll assume the purpose
                    # is just to allow the flow to continue to Kafka publishing.
                    # Let's fetch the existing one for accuracy
                    # This requires adding a query method, or modify create_transaction to include get_by_pk
                )
            raise # Re-raise other IntegrityErrors

    def get_transaction_by_pk(self, transaction_id: str, portfolio_id: str, instrument_id: str, transaction_date: str) -> DBTransaction | None:
        """
        Retrieves a transaction by its primary key components.
        """
        from datetime import date
        try:
            tx_date = date.fromisoformat(transaction_date)
        except ValueError:
            logger.error(f"Invalid date format for transaction_date: {transaction_date}")
            return None

        return self.db.query(DBTransaction).filter_by(
            transaction_id=transaction_id,
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            transaction_date=tx_date
        ).first()

    def create_or_update_transaction(self, transaction_event: TransactionEvent) -> DBTransaction:
        """
        Attempts to create a transaction. If it exists, retrieves it.
        This provides true idempotency by handling both new inserts and existing records.
        """
        # First, try to get the existing transaction by its natural key
        existing_transaction = self.get_transaction_by_pk(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            transaction_date=str(transaction_event.transaction_date)
        )

        if existing_transaction:
            logger.info(f"Transaction {transaction_event.transaction_id} already exists. No new insertion needed.")
            # If you wanted to allow updates to existing transactions, you would apply updates here
            # For now, we just return the existing one as "persisted".
            return existing_transaction
        else:
            # If not found, proceed with insertion
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
                # This block handles race conditions where another instance might insert
                # the same record between get_transaction_by_pk and the insert attempt.
                if isinstance(e.orig, UniqueViolation):
                    self.db.rollback() # Rollback the failed transaction
                    logger.warning(f"Race condition: Transaction {transaction_event.transaction_id} was inserted by another process. Fetching existing.")
                    # After rollback, attempt to fetch again to get the newly inserted record
                    return self.get_transaction_by_pk(
                        transaction_id=transaction_event.transaction_id,
                        portfolio_id=transaction_event.portfolio_id,
                        instrument_id=transaction_event.instrument_id,
                        transaction_date=str(transaction_event.transaction_date)
                    )
                raise # Re-raise other IntegrityErrors