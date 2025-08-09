# services/ingestion_service/app/DTOs/instrument_dto.py
from typing import List
from pydantic import BaseModel, Field, ConfigDict

class Instrument(BaseModel):
    """
    Represents a single financial instrument.
    """
    security_id: str = Field(..., alias="securityId", description="Unique identifier for the security.")
    name: str = Field(..., description="Full name of the instrument.")
    isin: str = Field(..., description="International Securities Identification Number.")
    currency: str = Field(..., alias="instrumentCurrency", description="The currency of the instrument.")
    product_type: str = Field(..., alias="productType", description="Type of product (e.g., bond, equity, fund).")

    model_config = ConfigDict(
        populate_by_name=True,  # Allows using either field name or alias
        json_schema_extra={
            "example": {
                "securityId": "SEC_AAPL",
                "name": "Apple Inc.",
                "isin": "US0378331005",
                "instrumentCurrency": "USD",
                "productType": "Equity"
            }
        }
    )

class InstrumentIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of instruments.
    """
    instruments: List[Instrument]