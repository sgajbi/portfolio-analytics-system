# src/services/query_service/app/dtos/position_analytics_dto.py
from datetime import date
from typing import List, Optional, Dict, Literal
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

class PositionValuation(BaseModel):
    """Represents the valuation details of a position."""
    market_value: MonetaryAmount = Field(..., alias="marketValue")
    cost_basis: MonetaryAmount = Field(..., alias="costBasis")
    unrealized_pnl: MonetaryAmount = Field(..., alias="unrealizedPnl")

    model_config = ConfigDict(populate_by_name=True)

class PositionPerformance(BaseModel):
    """Represents the performance of a single position for one period."""
    local_return: Optional[float] = Field(None, alias="localReturn")
    base_return: Optional[float] = Field(None, alias="baseReturn")

    model_config = ConfigDict(populate_by_name=True)

# --- Top-Level Position DTO ---

class EnrichedPosition(BaseModel):
    """Represents a single, fully enriched position in the response."""
    security_id: str = Field(..., alias="securityId")
    quantity: float
    weight: float
    held_since_date: date = Field(..., alias="heldSinceDate")
    
    instrument_details: Optional[PositionInstrumentDetails] = Field(None, alias="instrumentDetails")
    valuation: Optional[PositionValuation] = None
    income: Optional[MonetaryAmount] = None
    performance: Optional[Dict[str, PositionPerformance]] = None

    model_config = ConfigDict(populate_by_name=True)

# --- Request DTOs ---

class PositionAnalyticsSection(str, Enum):
    BASE = "BASE"
    INSTRUMENT_DETAILS = "INSTRUMENT_DETAILS"
    VALUATION = "VALUATION"
    INCOME = "INCOME"
    PERFORMANCE = "PERFORMANCE"

class PerformanceOptions(BaseModel):
    """Defines which performance periods to calculate."""
    periods: List[Literal["MTD", "QTD", "YTD", "ONE_YEAR", "SI"]]

class PositionAnalyticsRequest(BaseModel):
    """The main request body for the positions analytics endpoint."""
    as_of_date: date = Field(..., alias="asOfDate")
    sections: List[PositionAnalyticsSection]
    performance_options: Optional[PerformanceOptions] = Field(None, alias="performanceOptions")

    model_config = ConfigDict(populate_by_name=True)

# --- Response DTO ---

class PositionAnalyticsResponse(BaseModel):
    """The final, complete response object."""
    portfolio_id: str = Field(..., alias="portfolioId")
    as_of_date: date = Field(..., alias="asOfDate")
    total_market_value: float = Field(..., alias="totalMarketValue")
    positions: List[EnrichedPosition]

    model_config = ConfigDict(populate_by_name=True)