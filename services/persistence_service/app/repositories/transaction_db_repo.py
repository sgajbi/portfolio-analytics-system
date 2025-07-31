# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from sqlalchemy.orm import Session
# NEW IMPORT for UPSERT functionality
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_transaction(self, event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates a new transaction or updates an existing one using
        PostgreSQL's ON CONFLICT DO UPDATE (UPSERT) feature. This is more
        performant and robust than a separate select-then-insert.
        """
        # Create a dictionary of values from the event Pydantic model.
        insert_dict = event.model_dump()

        # Build the UPSERT statement.
        stmt = pg_insert(DBTransaction).values(
            **insert_dict
        ).on_conflict_do_update(
            # The conflict target is the unique 'transaction_id' column.
            index_elements=['transaction_id'],
            # If the transaction_id already exists, update all other fields.
            # This handles cases where a corrected transaction event is sent.
            set_={
                key: value for key, value in insert_dict.items() if key != 'transaction_id'
            }
        )

        try:
            # Execute the statement and commit is handled by the caller.
            self.db.execute(stmt)
            # Fetch the object back from the session to return it
            result = self.db.query(DBTransaction).filter_by(transaction_id=event.transaction_id).one()
            logger.info(f"Transaction '{result.transaction_id}' successfully upserted.")
            return result
        except Exception as e:
            logger.error(f"Failed to upsert transaction '{event.transaction_id}': {e}", exc_info=True)
            # Rollback is handled by the caller's session management.
            raise