import logging
from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from services.calculators.position_calculator.app.core.position_models import PositionState
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Position Calculator:
    Responsible for recalculating positions when transactions occur,
    including handling back-dated transactions and ensuring correct
    portfolio state.
    """

    @classmethod
    def calculate(cls, event: TransactionEvent, db_session: Session, repo=None):
        """
        Orchestrates recalculation logic for positions.
        Uses repo if provided (to support mocking in tests).
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date

        logger.info(f"[Calculate] Portfolio={portfolio_id}, Security={security_id}, Date={transaction_date}")

        # Use repo methods if provided
        if repo:
            anchor_position = repo.get_last_position_before(portfolio_id, security_id, transaction_date)
            transactions = repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
        else:
            anchor_position = cls.get_last_position_before(db_session, portfolio_id, security_id, transaction_date)
            transactions = cls.get_transactions_on_or_after(db_session, portfolio_id, security_id, transaction_date)

        new_positions = cls._calculate_new_positions(anchor_position, transactions)

        if repo:
            repo.save_positions(new_positions)
        else:
            db_session.add_all(new_positions)
            db_session.commit()

        logger.info(f"[Calculate] Completed recalculation for Portfolio={portfolio_id}, Security={security_id}")

    @staticmethod
    def get_last_position_before(db_session: Session, portfolio_id: str, security_id: str, transaction_date):
        return db_session.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id,
            PositionHistory.position_date < transaction_date.date()
        ).order_by(PositionHistory.position_date.desc()).first()

    @staticmethod
    def get_transactions_on_or_after(db_session: Session, portfolio_id: str, security_id: str, transaction_date):
        return db_session.query(DBTransaction).filter(
            DBTransaction.portfolio_id == portfolio_id,
            DBTransaction.security_id == security_id,
            DBTransaction.transaction_date >= transaction_date
        ).order_by(DBTransaction.transaction_date.asc()).all()

    @staticmethod
    def _calculate_new_positions(anchor_position, transactions: List[DBTransaction]) -> List[PositionHistory]:
        positions = []
        running_quantity = anchor_position.quantity if anchor_position else Decimal(0)
        running_cost_basis = anchor_position.cost_basis if anchor_position else Decimal(0)

        for txn in transactions:
            state = PositionCalculator.calculate_next_position(
                PositionState(quantity=running_quantity, cost_basis=running_cost_basis),
                txn
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
            if quantity > 0:
                avg_cost_per_unit = cost_basis / quantity
                cost_basis -= avg_cost_per_unit * transaction.quantity
            quantity -= transaction.quantity
        else:
            logger.info(f"[CalculateNext] Transaction type {txn_type} does not affect position.")

        return PositionState(quantity=quantity, cost_basis=cost_basis)
