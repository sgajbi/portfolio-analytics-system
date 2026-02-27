# services/ingestion_service/app/DTOs/market_price_dto.py
from datetime import date
from typing import List
from pydantic import BaseModel, Field, condecimal, ConfigDict
from decimal import Decimal

class MarketPrice(BaseModel):
    """
    Represents the market price for a security on a specific date.
    """
    security_id: str = Field(..., description="Unique identifier for the security.")
    price_date: date = Field(..., description="The date for which the price is valid.")
    price: condecimal(gt=Decimal(0)) = Field(..., description="The closing market price of the security.")
    currency: str = Field(..., description="The currency of the market price.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "securityId": "SEC_AAPL",
                "priceDate": "2025-07-26",
                "price": 175.50,
                "currency": "USD"
            }
        }
    )

class MarketPriceIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of market prices.
    """
    market_prices: List[MarketPrice]

