# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from sqlalchemy.orm import Session
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_transaction(self, event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates or updates a transaction using a
        get-then-update/create pattern.
        """
        try:
            db_transaction = self.db.query(DBTransaction).filter(DBTransaction.transaction_id == event.transaction_id).first()
            
            event_dict = event.model_dump()

            if db_transaction:
                # Update existing record
                for key, value in event_dict.items():
                    setattr(db_transaction, key, value)
                logger.info(f"Transaction '{event.transaction_id}' found, staging for update.")
            else:
                # Create new record
                db_transaction = DBTransaction(**event_dict)
                self.db.add(db_transaction)
                logger.info(f"Transaction '{event.transaction_id}' not found, staging for creation.")

            return db_transaction
        except Exception as e:
            logger.error(f"Failed to stage upsert for transaction '{event.transaction_id}': {e}", exc_info=True)
            raise