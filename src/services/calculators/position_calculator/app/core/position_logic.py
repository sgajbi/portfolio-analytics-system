# services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from ..core.position_models import PositionState
from portfolio_common.events import TransactionEvent
from ..repositories.position_repository import PositionRepository

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Position Calculator:
    Responsible for recalculating positions when transactions occur,
    including handling back-dated transactions and ensuring correct
    portfolio state with dual-currency cost basis.
    """

    @classmethod
    async def calculate(cls, event: TransactionEvent, db_session: AsyncSession, repo: PositionRepository) -> List[PositionHistory]:
        """
        Orchestrates recalculation logic for positions.
        This method stages changes in the session but does NOT commit them.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()

        logger.info(f"[Calculate] Portfolio={portfolio_id}, Security={security_id}, Date={transaction_date}")

        anchor_position = await repo.get_last_position_before(portfolio_id, security_id, transaction_date)
        transactions = await repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
        await repo.delete_positions_from(portfolio_id, security_id, transaction_date)
        
        new_positions = cls._calculate_new_positions(anchor_position, transactions)

        await repo.save_positions(new_positions)

        logger.info(f"[Calculate] Staged {len(new_positions)} new position records for Portfolio={portfolio_id}, Security={security_id}")
        return new_positions

    @staticmethod
    def _calculate_new_positions(anchor_position, transactions: List[DBTransaction]) -> List[PositionHistory]:
        positions = []
        running_quantity = anchor_position.quantity if anchor_position else Decimal(0)
        running_cost_basis = anchor_position.cost_basis if anchor_position else Decimal(0)
        running_cost_basis_local = anchor_position.cost_basis_local if anchor_position and anchor_position.cost_basis_local is not None else Decimal(0)

        for txn in transactions:
            txn_event = TransactionEvent.model_validate(txn)
            state = PositionCalculator.calculate_next_position(
                PositionState(
                    quantity=running_quantity, 
                    cost_basis=running_cost_basis,
                    cost_basis_local=running_cost_basis_local
                ),
                txn_event
            )

            running_quantity = state.quantity
            running_cost_basis = state.cost_basis
            running_cost_basis_local = state.cost_basis_local

            positions.append(PositionHistory(
                portfolio_id=txn.portfolio_id,
                security_id=txn.security_id,
                transaction_id=txn.transaction_id,
                position_date=txn.transaction_date.date(),
                quantity=running_quantity,
                cost_basis=running_cost_basis,
                cost_basis_local=running_cost_basis_local
            ))
        return positions

    @staticmethod
    def calculate_next_position(current_state: PositionState, transaction: TransactionEvent) -> PositionState:
        """
        Handles single transaction logic (BUY, SELL, etc.) for position changes in both currencies.
        """
        # --- START: Added for debugging ---
        logger.info(
            f"Calculating next position for txn_id={transaction.transaction_id} ({transaction.transaction_type}). "
            f"Current state: Qty={current_state.quantity}, CostLocal={current_state.cost_basis_local}"
        )
        # --- END: Added for debugging ---
        
        quantity = current_state.quantity
        cost_basis = current_state.cost_basis
        cost_basis_local = current_state.cost_basis_local

        txn_type = transaction.transaction_type.upper()
        
        net_cost = transaction.net_cost if transaction.net_cost is not None else Decimal(0)
        net_cost_local = transaction.net_cost_local if transaction.net_cost_local is not None else Decimal(0)

        if txn_type == "BUY":
            quantity += transaction.quantity
            cost_basis += net_cost
            cost_basis_local += net_cost_local
        elif txn_type == "SELL":
            if quantity != Decimal(0):
                proportion_sold = transaction.quantity / quantity
                cogs_base = cost_basis * proportion_sold
                cogs_local = cost_basis_local * proportion_sold
                
                cost_basis -= cogs_base
                cost_basis_local -= cogs_local
            quantity -= transaction.quantity
        
        else:
            logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")

        if quantity.is_zero():
            cost_basis = Decimal(0)
            cost_basis_local = Decimal(0)
            
        # --- START: Added for debugging ---
        logger.info(
            f"Finished calculating for txn_id={transaction.transaction_id}. "
            f"New state: Qty={quantity}, CostLocal={cost_basis_local}"
        )
        # --- END: Added for debugging ---

        return PositionState(quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local)