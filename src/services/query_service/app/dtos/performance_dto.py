# src/services/query_service/app/dtos/performance_dto.py
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal, Union, Optional, Dict
from datetime import date

# FIX: Import the missing constants
from performance_calculator_engine.constants import METRIC_BASIS_NET

# Define the allowed symbolic period types
PerformancePeriodType = Literal["YTD", "MTD", "QTD", "SI"]

class PerformancePeriod(BaseModel):
    """Defines a custom, explicit date range for a performance calculation."""
    start_date: date
    end_date: date

class PerformanceRequestPeriod(BaseModel):
    """
    Defines a single period to be calculated in a request.
    It has a name for the result key and specifies the period.
    """
    name: str = Field(..., description="A unique name for this calculation, used as the key in the response.")
    period: Union[PerformancePeriodType, PerformancePeriod] = Field(..., description="The period to calculate (e.g., 'YTD' or a custom date range).")

class PerformanceRequest(BaseModel):
    """The main request body for the performance calculation endpoint."""
    periods: List[PerformanceRequestPeriod] = Field(..., description="A list of performance periods to calculate.")
    metric_basis: Literal["NET", "GROSS"] = Field(METRIC_BASIS_NET, description="The basis for the return calculation (NET or GROSS).")
    reporting_currency: Optional[str] = Field(None, description="Optional currency to report results in (e.g., 'EUR'). Defaults to portfolio base currency.")

class PerformanceResult(BaseModel):
    """Contains the calculated performance for a single period."""
    return_pct: float = Field(..., alias="returnPct", description="The final time-weighted return for the period as a percentage.")
    
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )
        
class PerformanceResponse(BaseModel):
    """The final response object containing results for all requested periods."""
    portfolio_id: str
    results: Dict[str, PerformanceResult]