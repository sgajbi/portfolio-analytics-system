# services/query-service/app/dtos/valuation_dto.py
from pydantic import BaseModel, ConfigDict
from decimal import Decimal

class ValuationData(BaseModel):
    """
    Represents the valuation details for a position.
    """
    market_price: Decimal | None
    
    # In portfolio base currency
    market_value: Decimal | None
    unrealized_gain_loss: Decimal | None
    
    # In instrument's local currency
    market_value_local: Decimal | None
    unrealized_gain_loss_local: Decimal | None

    model_config = ConfigDict(
        from_attributes=True
    )