# src/logic/cost_basis_strategies.py
import logging
from typing import Protocol, Deque, Dict, Tuple, Optional
from collections import deque, defaultdict
from decimal import Decimal

from src.core.models.transaction import Transaction
from src.logic.cost_objects import CostLot

logger = logging.getLogger(__name__)

class CostBasisStrategy(Protocol):
    def add_buy_lot(self, transaction: Transaction): ...
    def consume_sell_quantity(self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal) -> Tuple[Decimal, Decimal, Optional[str]]: ...
    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal: ...
    def set_initial_lots(self, transactions: list[Transaction]): ...

class FIFOBasisStrategy:
    """
    Implements the First-In, First-Out (FIFO) cost basis method.
    """
    def __init__(self):
        self._open_lots: Dict[Tuple[str, str], Deque[CostLot]] = defaultdict(deque)
        logger.debug("FIFOBasisStrategy initialized.")

    def add_buy_lot(self, transaction: Transaction):
        if transaction.net_cost is None:
            raise ValueError(f"Buy transaction {transaction.transaction_id} must have net_cost calculated before adding as a lot.")
        if transaction.quantity == Decimal(0):
            return

        cost_per_share = transaction.net_cost / transaction.quantity
        new_lot = CostLot(
                transaction_id=transaction.transaction_id,
                quantity=transaction.quantity,
                cost_per_share=cost_per_share
            )
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._open_lots[key].append(new_lot)

    def consume_sell_quantity(self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal) -> Tuple[Decimal, Decimal, Optional[str]]:
        key = (portfolio_id, instrument_id)
        required_quantity = sell_quantity
        total_matched_cost = Decimal(0)
        consumed_quantity = Decimal(0)
        available_qty = self.get_available_quantity(portfolio_id=key[0], instrument_id=key[1])

        if required_quantity > available_qty:
            return (Decimal(0), Decimal(0), f"Sell quantity ({required_quantity}) exceeds available holdings ({available_qty}).")

        lots_for_instrument = self._open_lots[key]
        while required_quantity > 0 and lots_for_instrument:
            current_lot = lots_for_instrument[0]
            if current_lot.remaining_quantity >= required_quantity:
                cost_from_lot = required_quantity * current_lot.cost_per_share
                total_matched_cost += cost_from_lot
                consumed_quantity += required_quantity
                current_lot.remaining_quantity -= required_quantity
                required_quantity = Decimal(0)
                if current_lot.remaining_quantity == Decimal(0):
                    lots_for_instrument.popleft()
            else:
                cost_from_lot = current_lot.remaining_quantity * current_lot.cost_per_share
                total_matched_cost += cost_from_lot
                consumed_quantity += current_lot.remaining_quantity
                required_quantity -= current_lot.remaining_quantity
                lots_for_instrument.popleft()
        return total_matched_cost, consumed_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return sum(lot.remaining_quantity for lot in self._open_lots[key])

    def set_initial_lots(self, transactions: list[Transaction]):
        for txn in transactions:
            if txn.transaction_type == "BUY":
                self.add_buy_lot(txn)

class AverageCostBasisStrategy(CostBasisStrategy):
    """
    Implements the Average Cost (AVCO) method for tracking cost basis.
    """
    def __init__(self):
        self._holdings: Dict[Tuple[str, str], Dict[str, Decimal]] = defaultdict(lambda: {'total_qty': Decimal(0), 'total_cost': Decimal(0)})
        logger.debug("AverageCostBasisStrategy initialized.")

    def add_buy_lot(self, transaction: Transaction):
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._holdings[key]['total_qty'] += transaction.quantity
        self._holdings[key]['total_cost'] += transaction.net_cost

    def consume_sell_quantity(self, portfolio_id: str, instrument_id: str, required_quantity: Decimal) -> Tuple[Decimal, Decimal, Optional[str]]:
        key = (portfolio_id, instrument_id)
        total_qty = self._holdings[key]['total_qty']
        total_cost = self._holdings[key]['total_cost']

        if required_quantity > total_qty:
            return (Decimal(0), Decimal(0), f"Sell quantity ({required_quantity}) exceeds available average cost holdings ({total_qty}).")
        if total_qty == Decimal(0):
            return (Decimal(0), Decimal(0), "No holdings to sell against (Average Cost method).")

        average_cost_per_share = total_cost / total_qty
        matched_cost = required_quantity * average_cost_per_share
        self._holdings[key]['total_qty'] -= required_quantity
        self._holdings[key]['total_cost'] -= matched_cost
        return matched_cost, required_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        return self._holdings[key]['total_qty']

    def set_initial_lots(self, transactions: list[Transaction]):
        for txn in transactions:
            if txn.transaction_type == "BUY":
                self.add_buy_lot(txn)