# src/services/query_service/app/dtos/review_dto.py
from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

from .summary_dto import PnlSummary, AllocationSummary
from .position_dto import Position
from .transaction_dto import TransactionRecord
from .risk_dto import RiskResponse


class ReviewSection(str, Enum):
    OVERVIEW = "OVERVIEW"
    ALLOCATION = "ALLOCATION"
    PERFORMANCE = "PERFORMANCE"
    RISK_ANALYTICS = "RISK_ANALYTICS"
    INCOME_AND_ACTIVITY = "INCOME_AND_ACTIVITY"
    HOLDINGS = "HOLDINGS"
    TRANSACTIONS = "TRANSACTIONS"


class PortfolioReviewRequest(BaseModel):
    as_of_date: date
    sections: List[ReviewSection]


class OverviewSection(BaseModel):
    total_market_value: float
    total_cash: float
    risk_profile: str
    portfolio_type: str
    pnl_summary: PnlSummary


class HoldingsSection(BaseModel):
    holdings_by_asset_class: Dict[str, List[Position]] = Field(..., alias="holdingsByAssetClass")


class TransactionsSection(BaseModel):
    transactions_by_asset_class: Dict[str, List[TransactionRecord]] = Field(
        ..., alias="transactionsByAssetClass"
    )


# --- NEW: DTOs to handle NET & GROSS Performance ---
class ReviewPerformanceResult(BaseModel):
    """A DTO to hold both NET and GROSS returns for a single period."""

    start_date: date
    end_date: date
    net_cumulative_return: Optional[float] = None
    net_annualized_return: Optional[float] = None
    gross_cumulative_return: Optional[float] = None
    gross_annualized_return: Optional[float] = None
    attributes: Optional[Dict] = None  # Keeping attributes generic for simplicity


class ReviewPerformanceSection(BaseModel):
    """The complete performance section for the review response."""

    summary: Dict[str, ReviewPerformanceResult]


class IncomeAndActivitySection(BaseModel):
    """Consolidates the YTD income and activity summaries."""

    income_summary_ytd: Dict
    activity_summary_ytd: Dict


# --- END NEW ---


class PortfolioReviewResponse(BaseModel):
    portfolio_id: str
    as_of_date: date
    overview: Optional[OverviewSection] = None
    allocation: Optional[AllocationSummary] = None
    performance: Optional[ReviewPerformanceSection] = None
    risk_analytics: Optional[RiskResponse] = Field(None, alias="riskAnalytics")
    income_and_activity: Optional[IncomeAndActivitySection] = Field(None, alias="incomeAndActivity")
    holdings: Optional[HoldingsSection] = None
    transactions: Optional[TransactionsSection] = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
