from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import date
from typing import List

class MarketPriceRecord(BaseModel):
    """
    Represents a single market price record for an API response.
    """
    price_date: date
    price: Decimal
    currency: str
    
    model_config = ConfigDict(
        from_attributes=True
    )

class MarketPriceResponse(BaseModel):
    """
    Represents the API response for a market price query.
    """
    security_id: str = Field(..., description="The security ID for which prices are being returned.")
    prices: List[MarketPriceRecord] = Field(..., description="A list of market price records.")