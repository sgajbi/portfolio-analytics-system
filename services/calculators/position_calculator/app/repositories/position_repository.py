import logging
from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from portfolio_common.database_models import PositionHistory, Transaction

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles all database interactions for position calculation.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_last_position_before(self, portfolio_id: str, security_id: str, a_date: date) -> Optional[PositionHistory]:
        """
        Fetches the most recent position record for a security before a given date.
        This serves as the starting point for a recalculation.
        """
        return self.db.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date < a_date
        ).order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc()).first()

    def get_transactions_on_or_after(self, portfolio_id: str, security_id: str, a_date: date) -> List[Transaction]:
        """
        Retrieves all transactions for a security on or after a given date.
        """
        # We must cast the transaction_date (DateTime) to a Date for the comparison
        return self.db.query(Transaction).filter(
            Transaction.portfolio_id == portfolio_id,
            Transaction.security_id == security_id,
            func.date(Transaction.transaction_date) >= a_date
        ).all()

    def delete_positions_from(self, portfolio_id: str, security_id: str, a_date: date) -> int:
        """
        Deletes all position history records for a security from a given date onward.
        Returns the number of deleted rows.
        """
        num_deleted = self.db.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date >= a_date
        ).delete(synchronize_session=False)
        
        logger.info(f"Deleted {num_deleted} stale position records for {security_id} from {a_date} onward.")
        return num_deleted

    def save_positions(self, positions: List[PositionHistory]):
        """
        Bulk saves a list of new position history records to the database.
        """
        if not positions:
            return
        
        self.db.bulk_save_objects(positions)
        logger.info(f"Bulk saved {len(positions)} new position records.")