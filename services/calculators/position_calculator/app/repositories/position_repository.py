# services/calculators/position_calculator/app/repositories/position_repository.py
import logging
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, delete

from portfolio_common.database_models import PositionHistory, Transaction

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles all database interactions for position calculation.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_last_position_before(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> Optional[PositionHistory]:
        """
        Fetches most recent position before given date.
        This is used as the anchor for recalculation.
        """
        return (
            self.db.query(PositionHistory)
            .filter(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.position_date < a_date
            )
            .order_by(PositionHistory.position_date.desc(), PositionHistory.id.desc())
            .first()
        )

    def get_transactions_on_or_after(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> List[Transaction]:
        """
        Retrieves all transactions for security on or after given date.
        Uses full timestamp ordering to maintain sequence.
        """
        return (
            self.db.query(Transaction)
            .filter(
                Transaction.portfolio_id == portfolio_id,
                Transaction.security_id == security_id,
                # Cast the datetime field to a date for comparison
                func.date(Transaction.transaction_date) >= a_date
            )
            .order_by(Transaction.transaction_date.asc(), Transaction.id.asc())
            .all()
        )

    def delete_positions_from(
        self, portfolio_id: str, security_id: str, a_date: date
    ) -> int:
        """
        Deletes all position history records for a security from given date onward.
        Idempotent: ensures no duplicates if process retries.
        Returns number of deleted rows.
        """
        stmt = (
            delete(PositionHistory)
            .where(
                PositionHistory.portfolio_id == portfolio_id,
                PositionHistory.security_id == security_id,
                PositionHistory.position_date >= a_date
            )
        )
        result = self.db.execute(stmt)
        deleted_count = result.rowcount or 0

        logger.info(
            f"Deleted {deleted_count} stale position records "
            f"for {security_id} from {a_date} onward."
        )
        return deleted_count

    def save_positions(self, positions: List[PositionHistory]):
        """
        Bulk saves new position history records and flushes the session
        to populate auto-generated primary keys (like `id`).
        This method does not commit; it only stages and flushes the objects.
        """
        if not positions:
            logger.debug("No new positions to save.")
            return

        self.db.add_all(positions)
        # --- NEW: Flush session to persist records and populate IDs ---
        self.db.flush()
        logger.info(f"Staged and flushed {len(positions)} new position records for saving.")