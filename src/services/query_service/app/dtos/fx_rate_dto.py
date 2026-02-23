from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import List


class FxRateRecord(BaseModel):
    """
    Represents a single FX rate record for an API response.
    """

    rate_date: date
    rate: Decimal

    model_config = ConfigDict(from_attributes=True)


class FxRateResponse(BaseModel):
    """
    Represents the API response for an FX rate query.
    """

    from_currency: str = Field(..., description="The base currency.")
    to_currency: str = Field(..., description="The quote currency.")
    rates: List[FxRateRecord] = Field(..., description="A list of FX rate records.")
