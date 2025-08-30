# src/services/query_service/app/dtos/summary_dto.py
from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from enum import Enum

from .performance_dto import PerformanceRequestPeriod


class SummarySection(str, Enum):
    WEALTH = "WEALTH"
    ALLOCATION = "ALLOCATION"
    PNL = "PNL"
    INCOME = "INCOME"
    ACTIVITY = "ACTIVITY"

class AllocationDimension(str, Enum):
    ASSET_CLASS = "ASSET_CLASS"
    CURRENCY = "CURRENCY"
    SECTOR = "SECTOR"
    COUNTRY_OF_RISK = "COUNTRY_OF_RISK"
    MATURITY_BUCKET = "MATURITY_BUCKET"
    RATING = "RATING"


class SummaryRequest(BaseModel):
    as_of_date: date
    period: PerformanceRequestPeriod
    sections: List[SummarySection]
    allocation_dimensions: Optional[List[AllocationDimension]] = Field(None)


class ResponseScope(BaseModel):
    portfolio_id: str
    as_of_date: date
    period_start_date: date
    period_end_date: date

class WealthSummary(BaseModel):
    total_market_value: Decimal
    total_cash: Decimal

class PnlSummary(BaseModel):
    net_new_money: Decimal
    realized_pnl: Decimal
    unrealized_pnl_change: Decimal
    total_pnl: Decimal

class IncomeSummary(BaseModel):
    total_dividends: Decimal
    total_interest: Decimal

class ActivitySummary(BaseModel):
    total_inflows: Decimal
    total_outflows: Decimal
    total_fees: Decimal

class AllocationGroup(BaseModel):
    group: str
    market_value: Decimal
    weight: float # Weight is a percentage (0.0 to 1.0), float is appropriate

class AllocationSummary(BaseModel):
    by_asset_class: Optional[List[AllocationGroup]] = Field(None, alias="byAssetClass")
    by_currency: Optional[List[AllocationGroup]] = Field(None, alias="byCurrency")
    by_sector: Optional[List[AllocationGroup]] = Field(None, alias="bySector")
    by_country_of_risk: Optional[List[AllocationGroup]] = Field(None, alias="byCountryOfRisk")
    by_maturity_bucket: Optional[List[AllocationGroup]] = Field(None, alias="byMaturityBucket")
    by_rating: Optional[List[AllocationGroup]] = Field(None, alias="byRating")

    model_config = ConfigDict(populate_by_name=True)

class SummaryResponse(BaseModel):
    scope: ResponseScope
    wealth: Optional[WealthSummary] = None
    pnl_summary: Optional[PnlSummary] = Field(None, alias="pnlSummary")
    income_summary: Optional[IncomeSummary] = Field(None, alias="incomeSummary")
    activity_summary: Optional[ActivitySummary] = Field(None, alias="activitySummary")
    allocation: Optional[AllocationSummary] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True # For Decimal
    )