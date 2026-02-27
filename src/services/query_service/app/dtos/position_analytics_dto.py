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
    asset_class: Optional[str] = Field(None)
    sector: Optional[str] = None
    country_of_risk: Optional[str] = Field(None)
    currency: str

    model_config = ConfigDict()


class PositionValuationDetail(BaseModel):
    """Represents a single valuation metric (e.g., market value) in local and base currency."""

    local: MonetaryAmount
    base: MonetaryAmount


class PositionValuation(BaseModel):
    """Represents the valuation details of a position."""

    market_value: PositionValuationDetail = Field(...)
    cost_basis: PositionValuationDetail = Field(...)
    unrealized_pnl: PositionValuationDetail = Field(...)

    model_config = ConfigDict()


class EnrichedPosition(BaseModel):
    """Represents a single, fully enriched position in the response."""

    security_id: str = Field(...)
    quantity: float
    weight: float
    held_since_date: date = Field(...)

    instrument_details: Optional[PositionInstrumentDetails] = Field(None)
    valuation: Optional[PositionValuation] = None
    income: Optional[PositionValuationDetail] = None

    model_config = ConfigDict()


# --- Request DTOs ---


class PositionAnalyticsSection(str, Enum):
    BASE = "BASE"
    INSTRUMENT_DETAILS = "INSTRUMENT_DETAILS"
    VALUATION = "VALUATION"
    INCOME = "INCOME"


class PositionAnalyticsRequest(BaseModel):
    """The main request body for the positions analytics endpoint."""

    as_of_date: date = Field(...)
    sections: List[PositionAnalyticsSection]

    model_config = ConfigDict()


# --- Response DTO ---


class PositionAnalyticsResponse(BaseModel):
    """The final, complete response object."""

    portfolio_id: str = Field(...)
    as_of_date: date = Field(...)
    total_market_value: float = Field(...)
    positions: List[EnrichedPosition]

    model_config = ConfigDict()


