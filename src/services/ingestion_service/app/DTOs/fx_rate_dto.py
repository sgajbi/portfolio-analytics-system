# services/ingestion_service/app/DTOs/fx_rate_dto.py
from datetime import date
from typing import List
from pydantic import BaseModel, Field, condecimal, ConfigDict
from decimal import Decimal

class FxRate(BaseModel):
    """
    Represents a single foreign exchange rate between two currencies for a specific date.
    """
    from_currency: str = Field(..., description="The currency to convert from (e.g., USD).")
    to_currency: str = Field(..., description="The currency to convert to (e.g., SGD).")
    rate_date: date = Field(..., description="The date for which the rate is valid.")
    rate: condecimal(gt=Decimal(0)) = Field(..., description="The exchange rate (how many 'to_currency' units for one 'from_currency' unit).")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fromCurrency": "USD",
                "toCurrency": "SGD",
                "rateDate": "2025-07-26",
                "rate": 1.35
            }
        }
    )

class FxRateIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of FX rates.
    """
    fx_rates: List[FxRate]

