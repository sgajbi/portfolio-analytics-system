from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from portfolio_common.events import TransactionEvent
from .position_models import PositionState

logger = logging.getLogger(__name__)

class PositionCalculator:
    """
    A stateless calculator for determining the next position state.
    Uses Average Cost Method for BUY/SELL.
    Other transactions are recorded for downstream event triggering.
    """

    @staticmethod
    def _average_cost_per_unit(cost_basis: Decimal, quantity: Decimal) -> Decimal:
        """
        Safely computes average cost per unit.
        """
        try:
            if quantity > 0:
                return (cost_basis / quantity).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ZeroDivisionError):
            pass
        return Decimal(0)

    @staticmethod
    def calculate_next_position(
        previous_state: PositionState, 
        transaction: TransactionEvent
    ) -> PositionState:
        """
        Calculates the new position state based on previous state & transaction.
        """
        transaction_type = transaction.transaction_type.upper()

        if transaction_type == 'BUY':
            new_quantity = previous_state.quantity + transaction.quantity
            new_cost_basis = previous_state.cost_basis + (transaction.net_cost or Decimal(0))
            return PositionState(
                quantity=new_quantity, 
                cost_basis=new_cost_basis.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            )

        elif transaction_type == 'SELL':
            new_quantity = previous_state.quantity - transaction.quantity
            avg_cost = PositionCalculator._average_cost_per_unit(previous_state.cost_basis, previous_state.quantity)
            cost_of_goods_sold = avg_cost * transaction.quantity
            new_cost_basis = previous_state.cost_basis - cost_of_goods_sold

            # Ensure cost basis is not negative due to rounding
            if new_quantity <= 0:
                new_quantity = Decimal(0)
                new_cost_basis = Decimal(0)

            return PositionState(
                quantity=new_quantity.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP),
                cost_basis=new_cost_basis.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            )

        else:
            # All other transaction types (dividend, fee, corporate action, etc.)
            logger.debug(f"Transaction type '{transaction_type}' does not alter quantity/cost basis for security {transaction.security_id}")
            return PositionState(
                quantity=previous_state.quantity.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP),
                cost_basis=previous_state.cost_basis.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            )
