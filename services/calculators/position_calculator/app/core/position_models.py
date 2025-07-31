from pydantic import BaseModel
from decimal import Decimal

class PositionState(BaseModel):
    """
    Represents the state of a position at a point in time.
    This is a pure data object used for calculations.
    """
    quantity: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)