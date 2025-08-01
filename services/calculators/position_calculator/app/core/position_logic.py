# services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.core.position_models import PositionState
from portfolio_common.events import TransactionEvent, PositionHistoryPersistedEvent # NEW IMPORT

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Position Calculator:
    Responsible for recalculating positions when transactions occur,
    including handling back-dated transactions and ensuring correct
    portfolio state.
    """

    @classmethod
    def calculate(cls, event: TransactionEvent, db_session: Session, repo=None) -> List[PositionHistory]:
        """
        Orchestrates recalculation logic for positions.
        This method stages changes in the session but does NOT commit them.

        Args:
            event: The incoming transaction event triggering the recalculation.
            db_session: The SQLAlchemy session.
            repo: Optional repository for mocking in tests.

        Returns:
            A list of the new or updated PositionHistory records that were created.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date() # Use only the date part for consistency

        logger.info(f"[Calculate] Portfolio={portfolio_id}, Security={security_id}, Date={transaction_date}")

        if repo:
            anchor_position = repo.get_last_position_before(portfolio_id, security_id, transaction_date)
            transactions = repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
            repo.delete_positions_from(portfolio_id, security_id, transaction_date)
        else:
            # This logic will be handled by a real repository instance
            raise NotImplementedError("Direct DB access from logic is deprecated. Use a repository.")


        new_positions = cls._calculate_new_positions(anchor_position, transactions)

        if repo:
            # The repository's save method should also not commit.
            repo.save_positions(new_positions)
        else:
            # Fallback for old implementation, should be avoided.
            db_session.add_all(new_positions)

        logger.info(f"[Calculate] Staged {len(new_positions)} new position records for Portfolio={portfolio_id}, Security={security_id}")
        return new_positions

    @staticmethod
    def get_last_position_before(db_session: Session, portfolio_id: str, security_id: str, transaction_date):
        return db_session.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date < transaction_date
        ).order_by(PositionHistory.position_date.desc()).first()

    @staticmethod
    def get_transactions_on_or_after(db_session: Session, portfolio_id: str, security_id: str, transaction_date):
        return db_session.query(DBTransaction).filter(
            DBTransaction.portfolio_id == portfolio_id,
            DBTransaction.security_id == security_id,
            DBTransaction.transaction_date.cast(date) >= transaction_date
        ).order_by(DBTransaction.transaction_date.asc()).all()

    @staticmethod
    def _calculate_new_positions(anchor_position, transactions: List[DBTransaction]) -> List[PositionHistory]:
        positions = []
        running_quantity = anchor_position.quantity if anchor_position else Decimal(0)
        running_cost_basis = anchor_position.cost_basis if anchor_position else Decimal(0)

        for txn in transactions:
            # Convert DB model to event model for calculation
            txn_event = TransactionEvent.model_validate(txn)
            state = PositionCalculator.calculate_next_position(
                PositionState(quantity=running_quantity, cost_basis=running_cost_basis),
                txn_event
            )

            running_quantity = state.quantity
            running_cost_basis = state.cost_basis

            positions.append(PositionHistory(
                portfolio_id=txn.portfolio_id,
                security_id=txn.security_id,
                transaction_id=txn.transaction_id,
                position_date=txn.transaction_date.date(),
                quantity=running_quantity,
                cost_basis=running_cost_basis
            ))
        return positions

    @staticmethod
    def calculate_next_position(current_state: PositionState, transaction: TransactionEvent) -> PositionState:
        """
        Handles single transaction logic (BUY, SELL, etc.) for position changes.
        """
        quantity = current_state.quantity
        cost_basis = current_state.cost_basis

        txn_type = transaction.transaction_type.upper()
        net_cost = transaction.net_cost if transaction.net_cost is not None else Decimal(0)

        if txn_type == "BUY":
            quantity += transaction.quantity
            cost_basis += net_cost
        elif txn_type == "SELL":
            # Prevent division by zero if selling from a zero-quantity position (short-selling case)
            if quantity != Decimal(0):
                cost_of_goods_sold = (cost_basis / quantity) * transaction.quantity
                cost_basis -= cost_of_goods_sold
            quantity -= transaction.quantity
        else:
            logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")

        # Ensure cost basis doesn't become negative due to precision issues when quantity is zero
        if quantity == Decimal(0):
            cost_basis = Decimal(0)

        return PositionState(quantity=quantity, cost_basis=cost_basis)