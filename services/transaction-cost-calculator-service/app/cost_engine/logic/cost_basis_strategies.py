# src/logic/cost_basis_strategies.py
import logging
from typing import Protocol, Deque, Dict, Tuple, Optional
from collections import deque, defaultdict
from decimal import Decimal

from app.cost_engine.core.models.transaction import Transaction # Adjusted import
from app.cost_engine.logic.cost_objects import CostLot # Adjusted import

logger = logging.getLogger(__name__)

# --- Cost Basis Strategy Protocol ---

class CostBasisStrategy(Protocol):
    # ... (protocol definition remains the same)
    pass

# --- FIFO Cost Basis Strategy Implementation ---

class FIFOBasisStrategy:
    """
    Implements the First-In, First-Out (FIFO) cost basis method.
    Uses a deque to maintain the order of cost lots.
    """
    def __init__(self):
        # Stores cost lots: { (portfolio_id, instrument_id): Deque[CostLot] }
        self._open_lots: Dict[Tuple[str, str], Deque[CostLot]] = defaultdict(deque)
        logger.debug("FIFOBasisStrategy initialized.") # NEW LOG

    def add_buy_lot(self, transaction: Transaction):
        """
        Adds a new cost lot from a BUY transaction to the open lots for FIFO.
        Assumes transaction.net_cost is already calculated for BUYs.
        """
        if transaction.net_cost is None:
            raise ValueError(f"Buy transaction {transaction.transaction_id} must have net_cost calculated before adding as a lot.")

        quantity = transaction.quantity
        net_cost = transaction.net_cost

        # This quantity == 0 check is now redundant due to DispositionEngine filtering, but harmless
        if quantity == Decimal(0):
            logger.debug(f"FIFO: Skipping add_buy_lot for zero quantity transaction {transaction.transaction_id} (redundant check).") # NEW LOG
            return

        cost_per_share = net_cost / quantity
        new_lot = CostLot(
                transaction_id=transaction.transaction_id,
                quantity=quantity,
                cost_per_share=cost_per_share
            )
        key = (transaction.portfolio_id, transaction.instrument_id)
        self._open_lots[key].append(new_lot)
        logger.debug(f"FIFO: Added lot {new_lot.transaction_id} (Qty: {new_lot.original_quantity}, Cost/Share: {new_lot.cost_per_share:.4f}, NetCost: {transaction.net_cost:.2f}) for {key}. Current FIFO lots: {[l.transaction_id for l in self._open_lots[key]]}") # NEW LOG

    def consume_sell_quantity(
        self, portfolio_id: str, instrument_id: str, sell_quantity: Decimal
    ) -> Tuple[Decimal, Decimal, Optional[str]]:
        """
        Consumes quantity from open lots using FIFO method for a SELL transaction.
        Calculates the total matched cost and returns it along with consumed quantity.
        """
        key = (portfolio_id, instrument_id)
        required_quantity = sell_quantity
        total_matched_cost = Decimal(0)
        consumed_quantity = Decimal(0)

        available_qty = self.get_available_quantity(portfolio_id=key[0], instrument_id=key[1])
        logger.debug(f"FIFO Sell: Consuming {required_quantity:.2f} for {key}. Available: {available_qty:.2f}. Current FIFO lots: {[l.transaction_id for l in self._open_lots[key]]}") # NEW LOG

        if required_quantity > available_qty:
            logger.warning(f"FIFO Sell: Insufficient holdings for {key}. Required: {required_quantity:.2f}, Available: {available_qty:.2f}.") # NEW LOG
            return (
                Decimal(0),
                Decimal(0),
                f"Sell quantity ({required_quantity:.2f}) exceeds available holdings ({available_qty:.2f}) for instrument '{key[1]}' in portfolio '{key[0]}'."
            )

        lots_for_instrument = self._open_lots[key]

        while required_quantity > 0 and lots_for_instrument:
            current_lot = lots_for_instrument[0]
            logger.debug(f"  FIFO Sell: Processing lot {current_lot.transaction_id} (Remaining: {current_lot.remaining_quantity:.2f}, Cost/Share: {current_lot.cost_per_share:.4f}). Required: {required_quantity:.2f}.") # NEW LOG

            if current_lot.remaining_quantity >= required_quantity:
                cost_from_lot = required_quantity * current_lot.cost_per_share
                total_matched_cost += cost_from_lot
                consumed_quantity += required_quantity
                current_lot.remaining_quantity -= required_quantity
                required_quantity = Decimal(0)
                logger.debug(f"  FIFO Sell: Consumed {consumed_quantity:.2f} from {current_lot.transaction_id}. Lot remaining: {current_lot.remaining_quantity:.2f}. Matched cost so far: {total_matched_cost:.4f}.") # NEW LOG
                if current_lot.remaining_quantity == Decimal(0):
                    lots_for_instrument.popleft()
                    logger.debug(f"  FIFO Sell: Lot {current_lot.transaction_id} fully consumed and removed. Remaining lots: {[l.transaction_id for l in lots_for_instrument]}.") # NEW LOG
            else:
                cost_from_lot = current_lot.remaining_quantity * current_lot.cost_per_share
                total_matched_cost += cost_from_lot
                consumed_quantity += current_lot.remaining_quantity
                required_quantity -= current_lot.remaining_quantity
                lots_for_instrument.popleft()
                logger.debug(f"  FIFO Sell: Consumed all {current_lot.transaction_id} ({current_lot.original_quantity:.2f}). Remaining required: {required_quantity:.2f}. Matched cost so far: {total_matched_cost:.4f}. Remaining lots: {[l.transaction_id for l in lots_for_instrument]}.") # NEW LOG

        logger.debug(f"FIFO Sell: Finished consuming. Total matched cost: {total_matched_cost:.4f}, Consumed quantity: {consumed_quantity:.2f}.") # NEW LOG
        return total_matched_cost, consumed_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        key = (portfolio_id, instrument_id)
        qty = sum(lot.remaining_quantity for lot in self._open_lots[key])
        logger.debug(f"FIFO: Available quantity for {key}: {qty:.2f}.") # NEW LOG
        return qty

    def set_initial_lots(self, transactions: list[Transaction]):
        logger.debug("FIFOBasisStrategy: Setting initial lots:") # NEW LOG
        for txn in transactions:
            if txn.transaction_type == "BUY":
                self.add_buy_lot(txn)
                # The add_buy_lot already logs details, no need for redundant log here.
                # logger.debug(f"  FIFOBasisStrategy: Initial BUY added: ID={txn.transaction_id}, Qty={txn.quantity}, NetCost={txn.net_cost}.")
            else: # NEW LOG: To catch unexpected types
                logger.debug(f"  FIFOBasisStrategy: Skipping non-BUY transaction for initial lots: ID={txn.transaction_id}, Type={txn.transaction_type}.")

# --- Average Cost Basis Strategy Implementation ---

class AverageCostBasisStrategy(CostBasisStrategy):
    """
    Implements the Average Cost (AVCO) method for tracking cost basis.
    This method aggregates the cost of all shares purchased and divides by the total quantity
    to determine the average cost per share.
    """
    def __init__(self):
        self._holdings: Dict[Tuple[str, str], Dict[str, Decimal]] = defaultdict(lambda: {'total_qty': Decimal(0), 'total_cost': Decimal(0)})
        logger.debug("AverageCostBasisStrategy initialized.")


    def add_buy_lot(self, transaction: Transaction):
        """
        Adds a BUY transaction's quantity and cost to the aggregated holdings for average cost.
        """
        key = (transaction.portfolio_id, transaction.instrument_id)

        buy_quantity = transaction.quantity
        buy_net_cost = transaction.net_cost

        logger.debug(f"AVCO: Before BUY: Holdings for {key}: total_qty={self._holdings[key]['total_qty']:.2f}, total_cost={self._holdings[key]['total_cost']:.2f}") # MODIFIED LOG
        logger.debug(f"AVCO: Processing BUY {transaction.transaction_id}: quantity={buy_quantity:.2f}, net_cost={buy_net_cost:.2f}") # MODIFIED LOG


        self._holdings[key]['total_qty'] += buy_quantity
        self._holdings[key]['total_cost'] += buy_net_cost

        logger.debug(f"AVCO: After BUY: Holdings for {key}: total_qty={self._holdings[key]['total_qty']:.2f}, total_cost={self._holdings[key]['total_cost']:.2f}") # MODIFIED LOG


    def consume_sell_quantity(self, portfolio_id: str, instrument_id: str, required_quantity: Decimal) -> Tuple[Decimal, Decimal, Optional[str]]:
        """
        Calculates the cost basis for a SELL transaction using the average cost method.
        """
        key = (portfolio_id, instrument_id)
        total_qty = self._holdings[key]['total_qty']
        total_cost = self._holdings[key]['total_cost']
        logger.debug(f"AVCO Sell: Processing SELL for {key}: required_quantity={required_quantity:.2f}") # MODIFIED LOG
        logger.debug(f"AVCO Sell: Current holdings for SELL: total_qty={total_qty:.2f}, total_cost={total_cost:.2f}") # MODIFIED LOG

        if required_quantity > total_qty:
            logger.warning(f"AVCO Sell: Sell quantity ({required_quantity:.2f}) exceeds available average cost holdings ({total_qty:.2f}) for instrument '{key[1]}' in portfolio '{key[0]}'.") # MODIFIED LOG
            return (
                Decimal(0),
                Decimal(0),
                f"Sell quantity ({required_quantity:.2f}) exceeds available average cost holdings ({total_qty:.2f}) for instrument '{key[1]}' in portfolio '{key[0]}'."
            )

        if total_qty == Decimal(0):
             logger.warning(f"AVCO Sell: No holdings for instrument '{key[1]}' in portfolio '{key[0]}' to sell against (Average Cost method).") # NEW LOG
             return (
                Decimal(0),
                Decimal(0),
                f"No holdings for instrument '{key[1]}' in portfolio '{key[0]}' to sell against (Average Cost method).",
            )

        average_cost_per_share = total_cost / total_qty
        logger.debug(f"AVCO Sell: Calculated average_cost_per_share: {average_cost_per_share:.6f}") # MODIFIED LOG


        matched_cost = required_quantity * average_cost_per_share
        consumed_quantity = required_quantity
        logger.debug(f"AVCO Sell: Matched cost for sell quantity {consumed_quantity:.2f}: {matched_cost:.6f}") # MODIFIED LOG

        # Update holdings after sale
        self._holdings[key]['total_qty'] -= consumed_quantity
        self._holdings[key]['total_cost'] -= matched_cost # Deduct the cost basis of the sold shares
        logger.debug(f"AVCO Sell: After SELL: Holdings for {key}: total_qty={self._holdings[key]['total_qty']:.2f}, total_cost={self._holdings[key]['total_cost']:.2f}") # MODIFIED LOG

        return matched_cost, consumed_quantity, None

    def get_available_quantity(self, portfolio_id: str, instrument_id: str) -> Decimal:
        """
        Returns the total available quantity for a given instrument based on average cost holdings.
        """
        key = (portfolio_id, instrument_id)
        qty = self._holdings[key]['total_qty']
        logger.debug(f"AVCO: Available quantity for {key}: {qty:.2f}.") # NEW LOG
        return qty

    def set_initial_lots(self, transactions: list[Transaction]):
        """
        Initializes the Average Cost strategy with existing BUY transactions.
        """
        logger.debug("AverageCostBasisStrategy: Setting initial lots...") # MODIFIED LOG

        for txn in transactions:
            if txn.transaction_type == "BUY": # Use string literal for consistency with Pydantic model
                # Add existing BUY transactions to current holdings
                key = (txn.portfolio_id, txn.instrument_id)
                self._holdings[key]['total_qty'] += txn.quantity # No need for str(Decimal) here, it's already Decimal
                self._holdings[key]['total_cost'] += txn.net_cost # No need for str(Decimal) here, it's already Decimal
                logger.debug(f"  AverageCostBasisStrategy: Initial BUY added: Txn ID={txn.transaction_id}, quantity={txn.quantity:.2f}, net_cost={txn.net_cost:.2f}. Current holdings: total_qty={self._holdings[key]['total_qty']:.2f}, total_cost={self._holdings[key]['total_cost']:.2f}") # MODIFIED LOG
            else: # NEW LOG: To catch unexpected types
                logger.debug(f"  AverageCostBasisStrategy: Skipping non-BUY transaction for initial lots: ID={txn.transaction_id}, Type={txn.transaction_type}.")