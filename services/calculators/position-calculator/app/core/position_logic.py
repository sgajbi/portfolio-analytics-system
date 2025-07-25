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
        if transaction.transaction_type.upper() == 'BUY':
            new_quantity = previous_state.quantity + transaction.quantity
            # For a BUY, the net_cost of the transaction is added to the total cost basis
            new_cost_basis = previous_state.cost_basis + (transaction.net_cost or 0)
            return PositionState(quantity=new_quantity, cost_basis=new_cost_basis)

        elif transaction.transaction_type.upper() == 'SELL':
            new_quantity = previous_state.quantity - transaction.quantity
            
            # Calculate the cost of the shares being sold
            try:
                # This check prevents division by zero if we are selling from a zero quantity position (an error case)
                if previous_state.quantity > 0:
                    average_cost_per_share = previous_state.cost_basis / previous_state.quantity
                else:
                    average_cost_per_share = Decimal(0)
            except InvalidOperation:
                average_cost_per_share = Decimal(0)

            cost_of_goods_sold = average_cost_per_share * transaction.quantity
            new_cost_basis = previous_state.cost_basis - cost_of_goods_sold
            return PositionState(quantity=new_quantity, cost_basis=new_cost_basis)
        
        # For other transaction types, we assume they don't affect quantity or cost basis
        return previous_state