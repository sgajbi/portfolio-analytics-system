# src/services/query_service/app/dtos/position_analytics_dto.py
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# --- Helper DTOs for nested structures ---


class MonetaryAmount(BaseModel):
    """Represents a monetary amount with its currency."""

    amount: float
    currency: str


class PositionInstrumentDetails(BaseModel):
    """Represents the instrument reference data for a position."""

    name: str
    isin: str
    asset_class: Optional[str] = Field(None, alias="assetClass")
    sector: Optional[str] = None
    country_of_risk: Optional[str] = Field(None, alias="countryOfRisk")
    currency: str

    model_config = ConfigDict(populate_by_name=True)


class PositionValuationDetail(BaseModel):
    """Represents a single valuation metric (e.g., market value) in local and base currency."""

    local: MonetaryAmount
    base: MonetaryAmount


class PositionValuation(BaseModel):
    """Represents the valuation details of a position."""

    market_value: PositionValuationDetail = Field(..., alias="marketValue")
    cost_basis: PositionValuationDetail = Field(..., alias="costBasis")
    unrealized_pnl: PositionValuationDetail = Field(..., alias="unrealizedPnl")

    model_config = ConfigDict(populate_by_name=True)


class EnrichedPosition(BaseModel):
    """Represents a single, fully enriched position in the response."""

    security_id: str = Field(..., alias="securityId")
    quantity: float
    weight: float
    held_since_date: date = Field(..., alias="heldSinceDate")

    instrument_details: Optional[PositionInstrumentDetails] = Field(None, alias="instrumentDetails")
    valuation: Optional[PositionValuation] = None
    income: Optional[PositionValuationDetail] = None

    model_config = ConfigDict(populate_by_name=True)


# --- Request DTOs ---


class PositionAnalyticsSection(str, Enum):
    BASE = "BASE"
    INSTRUMENT_DETAILS = "INSTRUMENT_DETAILS"
    VALUATION = "VALUATION"
    INCOME = "INCOME"


class PositionAnalyticsRequest(BaseModel):
    """The main request body for the positions analytics endpoint."""

    as_of_date: date = Field(..., alias="asOfDate")
    sections: List[PositionAnalyticsSection]

    model_config = ConfigDict(populate_by_name=True)


# --- Response DTO ---


class PositionAnalyticsResponse(BaseModel):
    """The final, complete response object."""

    portfolio_id: str = Field(..., alias="portfolioId")
    as_of_date: date = Field(..., alias="asOfDate")
    total_market_value: float = Field(..., alias="totalMarketValue")
    positions: List[EnrichedPosition]

    model_config = ConfigDict(populate_by_name=True)
