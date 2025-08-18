# src/services/query_service/app/dtos/performance_dto.py
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Literal, Union, Optional, Dict, Annotated
from datetime import date
from decimal import Decimal

# --- API Request Models ---

class PerformanceRequestScope(BaseModel):
    """Defines the overall context for the performance calculation."""
    as_of_date: date = Field(default_factory=date.today, description="The reference date for calculations like MTD, YTD. Defaults to today.")
    reporting_currency: Optional[str] = Field(None, description="ISO currency code for reporting. Defaults to portfolio's base currency.")
    net_or_gross: Literal["NET", "GROSS"] = Field("NET", description="Specifies whether to calculate Net or Gross performance.")

class PeriodBase(BaseModel):
    """Base model for a period definition to enable discriminated union."""
    name: Optional[str] = Field(None, description="A unique name for this period, used as a key in the response. If omitted, a default name will be generated.")
    breakdown: Optional[Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"]] = Field(None, description="Optional breakdown of results for this period.")

class ExplicitPeriod(PeriodBase):
    """Defines a custom period with explicit start and end dates."""
    type: Literal["EXPLICIT"]
    from_date: date = Field(..., alias="from", description="The start date of the period (inclusive).")
    to_date: date = Field(..., alias="to", description="The end date of the period (inclusive).")

class YearPeriod(PeriodBase):
    """Defines a calendar year period."""
    type: Literal["YEAR"]
    year: int = Field(..., gt=1900, lt=2100, description="The calendar year to calculate performance for.")

class StandardPeriod(PeriodBase):
    """Defines standard, relative period types."""
    type: Literal["MTD", "QTD", "YTD", "THREE_YEAR", "FIVE_YEAR", "SI"]

# A discriminated union to handle different types of period requests
PerformanceRequestPeriod = Annotated[
    Union[ExplicitPeriod, YearPeriod, StandardPeriod],
    Field(discriminator="type")
]

class PerformanceRequestOptions(BaseModel):
    """Defines options for tailoring the response."""
    include_annualized: bool = Field(True, description="Whether to include annualized returns for periods over one year.")
    include_cumulative: bool = Field(True, description="Whether to include the total cumulative return for each period.")
    include_attributes: bool = Field(False, description="Whether to include financial attributes like market values and cashflows.")

class PerformanceRequest(BaseModel):
    """The main request body for the performance calculation endpoint."""
    scope: PerformanceRequestScope
    periods: List[PerformanceRequestPeriod]
    options: PerformanceRequestOptions = Field(default_factory=PerformanceRequestOptions)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "scope": {
                    "as_of_date": "2025-08-13",
                    "reporting_currency": "USD",
                    "net_or_gross": "NET"
                },
                "periods": [
                    {"name": "Year to Date", "type": "YTD", "breakdown": "MONTHLY"},
                    {"name": "Last Month", "type": "EXPLICIT", "from": "2025-07-01", "to": "2025-07-31"},
                    {"type": "THREE_YEAR"},
                ],
                "options": {
                    "include_annualized": True,
                    "include_cumulative": True,
                    "include_attributes": True
                }
            }
        }
    )


# --- API Response Models ---

class PerformanceAttributes(BaseModel):
    """Holds the raw financial attributes for a given period."""
    begin_market_value: Optional[Decimal] = None
    end_market_value: Optional[Decimal] = None
    total_cashflow: Optional[Decimal] = None
    fees: Optional[Decimal] = None
    
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class PerformanceResult(BaseModel):
    """Contains the calculated performance and attributes for a single period or sub-period."""
    start_date: date
    end_date: date
    cumulative_return: Optional[float] = Field(None, description="The total geometric return for the period as a percentage.")
    annualized_return: Optional[float] = Field(None, description="The annualized return as a percentage, if applicable.")
    attributes: Optional[PerformanceAttributes] = None

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

class PerformanceBreakdown(BaseModel):
    """Contains the detailed breakdown results for a single requested period."""
    breakdown_type: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"]
    results: List[PerformanceResult]

class PerformanceResponse(BaseModel):
    """The final, complete response object."""
    scope: PerformanceRequestScope
    summary: Dict[str, PerformanceResult] = Field(..., description="A dictionary mapping the requested period name to its summary result.")
    breakdowns: Optional[Dict[str, PerformanceBreakdown]] = Field(None, description="A dictionary containing detailed breakdowns, if requested.")