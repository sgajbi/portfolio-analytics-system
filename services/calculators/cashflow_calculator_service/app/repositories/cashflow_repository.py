import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from portfolio_common.database_models import Cashflow

logger = logging.getLogger(__name__)

class CashflowRepository:
    """
    Handles all database operations for the Cashflow model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_cashflow(self, cashflow: Cashflow) -> Cashflow | None:
        """
        Saves a new Cashflow record to the database within a managed transaction.
        """
        try:
            self.db.add(cashflow)
            self.db.flush() # Flushes the change to the DB to get IDs, etc.
            self.db.refresh(cashflow)
            logger.info(f"Successfully staged cashflow record for transaction_id: {cashflow.transaction_id}")
            return cashflow
        except IntegrityError:
            # This handles the case where the cashflow might already exist due to a retry.
            # The transaction will be rolled back by the consumer's context manager.
            logger.warning(
                f"A cashflow for transaction_id '{cashflow.transaction_id}' may already exist. "
                "The transaction will be rolled back."
            )
            raise # Re-raise for the context manager to handle
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while staging cashflow for txn {cashflow.transaction_id}: {e}",
                exc_info=True
            )
            raise 