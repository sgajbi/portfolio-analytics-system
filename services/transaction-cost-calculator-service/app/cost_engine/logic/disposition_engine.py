# src/logic/disposition_engine.py

from collections import defaultdict, deque
from typing import Deque, Optional, Tuple, Dict
from decimal import Decimal
from app.cost_engine.core.models.transaction import Transaction # Adjusted import
from app.cost_engine.core.enums.transaction_type import TransactionType # Adjusted import
from app.cost_engine.logic.cost_basis_strategies import CostBasisStrategy, FIFOBasisStrategy, AverageCostBasisStrategy # Adjusted import
from app.cost_engine.logic.cost_objects import CostLot # Adjusted import
import logging

logger = logging.getLogger(__name__) # NEW: Initialize logger

class DispositionEngine:
    """
    Manages the 'cost lots' for instruments within portfolios,
    delegating the actual cost basis calculation logic to a specific strategy.
    """
    def __init__(self, cost_basis_strategy: CostBasisStrategy):
        self._cost_basis_strategy = cost_basis_strategy

    def add_buy_lot(self, transaction: Transaction):
        """
        Delegates adding a new BUY transaction to the active cost basis strategy.
        Prevents adding lots with zero quantity.
        """
        logger.debug(f"DispositionEngine: Attempting to add buy lot for TXN ID: {transaction.transaction_id}, Qty: {transaction.quantity}") # NEW LOG
        if transaction.quantity == Decimal(0):
            logger.debug(f"DispositionEngine: Skipping add_buy_lot for zero quantity TXN ID: {transaction.transaction_id}.") # NEW LOG
            return
        self._cost_basis_strategy.add_buy_lot(transaction)
        logger.debug(f"DispositionEngine: Successfully delegated add_buy_lot for TXN ID: {transaction.transaction_id}.") # NEW LOG

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        """
        Delegates getting available quantity to the active cost basis strategy.
        """
        qty = self._cost_basis_strategy.get_available_quantity(portfolio_id, instrument_id)
        logger.debug(f"DispositionEngine: Available quantity for {(portfolio_id, instrument_id)}: {qty}") # NEW LOG
        return qty

    def consume_sell_quantity(
        self, transaction: Transaction
    ) -> Tuple[Decimal, Decimal, Optional[str]]:
        """
        Delegates consuming quantity for a SELL transaction to the active cost basis strategy.
        """
        sell_quantity = Decimal(str(transaction.quantity))
        logger.debug(f"DispositionEngine: Consuming sell quantity for TXN ID: {transaction.transaction_id}, Qty: {sell_quantity}") # NEW LOG
        total_matched_cost, consumed_quantity, error_reason = self._cost_basis_strategy.consume_sell_quantity(
            transaction.portfolio_id, transaction.instrument_id, sell_quantity
        )
        if error_reason: # NEW LOG
            logger.debug(f"DispositionEngine: Consumption failed for TXN ID: {transaction.transaction_id}, Error: {error_reason}")
        else:
            logger.debug(f"DispositionEngine: Consumption successful for TXN ID: {transaction.transaction_id}, Matched Cost: {total_matched_cost}, Consumed Qty: {consumed_quantity}")
        return total_matched_cost, consumed_quantity, error_reason

    def set_initial_lots(self, transactions: list[Transaction]):
        """
        Delegates initializing the disposition engine with existing BUY transactions
        to the active cost basis strategy.
        """
        logger.debug("DispositionEngine: Initializing with existing lots (before filtering for buys with quantity > 0):") # NEW LOG
        for txn in transactions: # NEW LOGGING LOOP
            logger.debug(f"  Received for initial: ID={txn.transaction_id}, Type={txn.transaction_type}, Qty={txn.quantity}, NetCost={txn.net_cost}.") # NEW LOG

        filtered_buys = [
            txn for txn in transactions if txn.transaction_type == TransactionType.BUY and txn.quantity > Decimal(0)
        ]
        logger.debug(f"DispositionEngine: Filtered initial BUY lots to pass to strategy: {[txn.transaction_id for txn in filtered_buys]}") # NEW LOG

        self._cost_basis_strategy.set_initial_lots(filtered_buys)

    def get_all_open_lots(self) -> Dict[Tuple[str, str], Deque[CostLot]]:
        """
        For debugging or testing: returns the current state of all open lots.
        Note: This method might not be directly applicable or fully representative
        for non-FIFO strategies (e.g., Average Cost).
        """
        if isinstance(self._cost_basis_strategy, FIFOBasisStrategy):
            logger.debug(f"DispositionEngine: Retrieving all open FIFO lots for debugging.") # NEW LOG
            return self._cost_basis_strategy._open_lots
        elif isinstance(self._cost_basis_strategy, AverageCostBasisStrategy):
             raise NotImplementedError("get_all_open_lots is not applicable for AverageCostBasisStrategy. Consider adding a method like get_all_current_holdings_average_cost to the strategy if needed.")
        else:
            raise NotImplementedError(f"get_all_open_lots not implemented for {type(self._cost_basis_strategy).__name__}")