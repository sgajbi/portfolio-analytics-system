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
        Saves a new Cashflow record to the database.

        This operation is idempotent. If a cashflow for the given transaction_id
        already exists, the database's unique constraint will raise an
        IntegrityError, which is caught and handled gracefully.

        Args:
            cashflow: The Cashflow object to be persisted.

        Returns:
            The persisted Cashflow object (either newly created or the
            existing one), or None if an unexpected error occurs.
        """
        try:
            self.db.add(cashflow)
            self.db.commit()
            self.db.refresh(cashflow)
            logger.info(f"Successfully inserted cashflow record for transaction_id: {cashflow.transaction_id}")
            return cashflow
        except IntegrityError:
            self.db.rollback()
            logger.warning(
                f"Cashflow for transaction_id '{cashflow.transaction_id}' already exists. "
                "Skipping creation due to unique constraint."
            )
            # Query and return the existing one to fulfill the return contract
            return self.db.query(Cashflow).filter(
                Cashflow.transaction_id == cashflow.transaction_id
            ).first()
        except Exception as e:
            self.db.rollback()
            logger.error(
                f"An unexpected error occurred while saving cashflow for txn {cashflow.transaction_id}: {e}",
                exc_info=True
            )
            return None