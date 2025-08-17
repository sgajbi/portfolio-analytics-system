# src/services/query_service/app/dtos/performance_dto.py
from pydantic import BaseModel, Field
from typing import List, Literal, Union, Optional, Dict
from datetime import date

class PerformancePeriod(BaseModel):
    type: Literal["EXPLICIT", "CALENDAR_YEAR"]
    start_date: date
    end_date: date

PerformancePeriodType = Literal["YTD", "QTD", "MTD", "SI"]

class PerformanceRequest(BaseModel):
    periods: List[Union[PerformancePeriodType, PerformancePeriod]]
    metric_basis: Literal["NET", "GROSS"] = "NET"

class PerformanceResult(BaseModel):
    return_pct: float = Field(..., alias="returnPct")

    class Config:
        populate_by_name = True
        
class PerformanceResponse(BaseModel):
    portfolio_id: str
    results: Dict[str, PerformanceResult]