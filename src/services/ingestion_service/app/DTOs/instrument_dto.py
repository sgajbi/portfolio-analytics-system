# services/ingestion_service/app/DTOs/instrument_dto.py
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import date

class Instrument(BaseModel):
    """
    Represents a single financial instrument.
"""
    security_id: str = Field(..., description="Unique identifier for the security.")
    name: str = Field(..., description="Full name of the instrument.")
    isin: str = Field(..., description="International Securities Identification Number.")
    currency: str = Field(..., description="The currency of the instrument.")
    product_type: str = Field(..., description="Type of product (e.g., bond, equity, fund).")
    asset_class: Optional[str] = Field(None, description="High-level, standardized category (e.g., 'Equity', 'Fixed Income').")
    sector: Optional[str] = Field(None, description="Industry sector for equities (e.g., 'Technology').")
    country_of_risk: Optional[str] = Field(None, description="The country of primary risk exposure.")
    rating: Optional[str] = Field(None, description="Credit rating for fixed income instruments (e.g., 'AAA').")
    maturity_date: Optional[date] = Field(None, description="Maturity date for fixed income instruments.")
    issuer_id: Optional[str] = Field(None, description="Identifier for the direct issuer of the security.")
    ultimate_parent_issuer_id: Optional[str] = Field(None, description="Identifier for the ultimate parent of the issuer.")

    model_config = ConfigDict(
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
                "maturityDate": None,
                "issuerId": "ISSUER_BARC",
                "ultimateParentIssuerId": "ULTIMATE_BARC"
            }
        }
    )

class InstrumentIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of instruments.
    """
    instruments: List[Instrument]

