# src/logic/cost_objects.py

from decimal import Decimal


class CostLot:
    """Represents a single 'lot' of securities acquired through a BUY transaction."""
    def __init__(self, transaction_id: str, quantity: Decimal, cost_per_share: Decimal):
        self.transaction_id = transaction_id
        self.original_quantity = quantity
        self.remaining_quantity = quantity
        self.cost_per_share = cost_per_share

    @property
    def total_cost(self) -> Decimal:
        """Calculates the total cost of the original lot."""
        return self.original_quantity * self.cost_per_share

    def __repr__(self) -> str:
        return (f"CostLot(txn_id='{self.transaction_id}', "
                f"original_qty={self.original_quantity:.2f}, "
                f"remaining_qty={self.remaining_quantity:.2f}, "
                f"cost_per_share={self.cost_per_share:.4f})")