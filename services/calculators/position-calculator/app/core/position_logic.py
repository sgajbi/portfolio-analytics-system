from decimal import Decimal, InvalidOperation
from portfolio_common.events import TransactionEvent
from .position_models import PositionState

class PositionCalculator:
    """
    A stateless calculator for determining the next position state.
    """
    @staticmethod
    def calculate_next_position(
        previous_state: PositionState, 
        transaction: TransactionEvent
    ) -> PositionState:
        """
        Calculates the new position state based on the previous state and a new transaction.
        Uses the Average Cost method.
        """
        transaction_type = transaction.transaction_type.upper()

        if transaction_type == 'BUY':
            new_quantity = previous_state.quantity + transaction.quantity
            # For a BUY, the net_cost of the transaction is added to the total cost basis
            new_cost_basis = previous_state.cost_basis + (transaction.net_cost or 0)
            return PositionState(quantity=new_quantity, cost_basis=new_cost_basis)

        elif transaction_type == 'SELL':
            new_quantity = previous_state.quantity - transaction.quantity
            
            try:
                if previous_state.quantity > 0:
                    average_cost_per_share = previous_state.cost_basis / previous_state.quantity
                else:
                    average_cost_per_share = Decimal(0)
            except InvalidOperation:
                average_cost_per_share = Decimal(0)

            cost_of_goods_sold = average_cost_per_share * transaction.quantity
            new_cost_basis = previous_state.cost_basis - cost_of_goods_sold
            return PositionState(quantity=new_quantity, cost_basis=new_cost_basis)
        
        # --- DEFINITIVE FIX ---
        # For other transaction types (FEE, DIVIDEND, etc.), they represent
        # a change in the cash position. We must create a new record for that day,
        # but the quantity and cost_basis of the "CASH" instrument itself do not change.
        # This ensures a position history record is created, which triggers downstream processes.
        else:
            return PositionState(
                quantity=previous_state.quantity, 
                cost_basis=previous_state.cost_basis
            )