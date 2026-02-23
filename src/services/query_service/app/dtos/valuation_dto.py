# services/query-service/app/dtos/valuation_dto.py
from pydantic import BaseModel, ConfigDict


class ValuationData(BaseModel):
    """
    Represents the valuation details for a position.
    """

    market_price: float | None

    # In portfolio base currency
    market_value: float | None
    unrealized_gain_loss: float | None

    # In instrument's local currency
    market_value_local: float | None
    unrealized_gain_loss_local: float | None

    model_config = ConfigDict(from_attributes=True)
