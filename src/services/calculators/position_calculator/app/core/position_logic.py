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
        Orchestrates recalculation logic for a single transaction event.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()

        # In case of a back-dated transaction, we must clear out any now-stale history
        await repo.delete_positions_from(portfolio_id, security_id, transaction_date)

        # Get the state of the position right before this transaction occurred
        anchor_position = await repo.get_last_position_before(portfolio_id, security_id, transaction_date)

        # Create the initial state for the calculation
        initial_state = PositionState(
            quantity=anchor_position.quantity if anchor_position else Decimal(0),
            cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0),
            cost_basis_local=anchor_position.cost_basis_local if anchor_position and anchor_position.cost_basis_local is not None else Decimal(0)
        )

        # Calculate the new state by applying only the current transaction
        new_state = cls.calculate_next_position(initial_state, event)

        # Create the new history record for this transaction
        new_position = PositionHistory(
            portfolio_id=event.portfolio_id,
            security_id=event.security_id,
            transaction_id=event.transaction_id,
            position_date=event.transaction_date.date(),
            quantity=new_state.quantity,
            cost_basis=new_state.cost_basis,
            cost_basis_local=new_state.cost_basis_local
        )
        
        await repo.save_positions([new_position])

        logger.info(f"[Calculate] Staged 1 new position record for Portfolio={portfolio_id}, Security={security_id}")
        return [new_position]

    @staticmethod
    def _calculate_new_positions(anchor_position, transactions: List[DBTransaction]) -> List[PositionHistory]:
        # This method is no longer used but kept for potential future enhancements
        # around batch processing. It is not part of the main execution path now.
        pass

    @staticmethod
    def calculate_next_position(current_state: PositionState, transaction: TransactionEvent) -> PositionState:
        """
        Handles single transaction logic (BUY, SELL, etc.) for position changes in both currencies.
        """
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
        elif txn_type in ["DEPOSIT", "TRANSFER_IN"]:
            # These are cash inflows that increase the cash position quantity and cost basis
            quantity += transaction.gross_transaction_amount
            cost_basis += transaction.gross_transaction_amount
            cost_basis_local += transaction.gross_transaction_amount
        elif txn_type == "SELL":
            if quantity != Decimal(0):
                proportion_sold = transaction.quantity / quantity
                cogs_base = cost_basis * proportion_sold
                cogs_local = cost_basis_local * proportion_sold
                
                cost_basis -= cogs_base
                cost_basis_local -= cogs_local
            quantity -= transaction.quantity
        
        elif txn_type in ["FEE", "TAX", "TRANSFER_OUT"]:
            # These are cash outflows, decrease quantity and cost (value)
            quantity -= transaction.gross_transaction_amount
            cost_basis -= transaction.gross_transaction_amount
            cost_basis_local -= transaction.gross_transaction_amount
        
        else:
            logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")

        if quantity.is_zero():
            cost_basis = Decimal(0)
            cost_basis_local = Decimal(0)

        return PositionState(quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local)