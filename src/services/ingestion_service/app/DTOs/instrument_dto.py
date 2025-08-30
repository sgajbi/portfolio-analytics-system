# services/ingestion_service/app/DTOs/instrument_dto.py
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import date

class Instrument(BaseModel):
    """
    Represents a single financial instrument.
    """
    security_id: str = Field(..., alias="securityId", description="Unique identifier for the security.")
    name: str = Field(..., description="Full name of the instrument.")
    isin: str = Field(..., description="International Securities Identification Number.")
    currency: str = Field(..., alias="instrumentCurrency", description="The currency of the instrument.")
    product_type: str = Field(..., alias="productType", description="Type of product (e.g., bond, equity, fund).")
    asset_class: Optional[str] = Field(None, alias="assetClass", description="High-level, standardized category (e.g., 'Equity', 'Fixed Income').")
    sector: Optional[str] = Field(None, description="Industry sector for equities (e.g., 'Technology').")
    country_of_risk: Optional[str] = Field(None, alias="countryOfRisk", description="The country of primary risk exposure.")
    rating: Optional[str] = Field(None, description="Credit rating for fixed income instruments (e.g., 'AAA').")
    maturity_date: Optional[date] = Field(None, alias="maturityDate", description="Maturity date for fixed income instruments.")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "securityId": "SEC_BARC_PERP",
                "name": "Barclays PLC 8% Perpetual",
                "isin": "US06738E2046",
                "instrumentCurrency": "USD",
                "productType": "Bond",
                "assetClass": "Fixed Income",
                "sector": "Financials",
                "countryOfRisk": "GB",
                "rating": "BB+",
                "maturityDate": None
            }
        }
    )

class InstrumentIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of instruments.
    """
    instruments: List[Instrument]