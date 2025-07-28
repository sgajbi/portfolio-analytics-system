from pydantic import BaseModel, ConfigDict
from decimal import Decimal

class ValuationData(BaseModel):
    """
    Represents the valuation details for a position.
    """
    market_price: Decimal | None
    market_value: Decimal | None
    unrealized_gain_loss: Decimal | None

    model_config = ConfigDict(
        from_attributes=True
    )