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
            self.db.flush() # Flushes to assign DB-generated defaults like 'id'
            self.db.refresh(cashflow) # <-- THE FIX: Refresh the object to load all columns
            logger.info(f"Successfully staged cashflow record for transaction_id: {cashflow.transaction_id}")
            return cashflow
        except IntegrityError:
            logger.warning(
                f"A cashflow for transaction_id '{cashflow.transaction_id}' may already exist. "
                "The transaction will be rolled back."
            )
            raise 
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while staging cashflow for txn {cashflow.transaction_id}: {e}",
                exc_info=True
            )
            raise