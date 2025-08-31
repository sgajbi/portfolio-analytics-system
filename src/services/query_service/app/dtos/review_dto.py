# src/services/query_service/app/dtos/review_dto.py
from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from enum import Enum

from .summary_dto import WealthSummary, PnlSummary, IncomeSummary, ActivitySummary, AllocationSummary
from .performance_dto import PerformanceResponse
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
    transactions_by_asset_class: Dict[str, List[TransactionRecord]] = Field(..., alias="transactionsByAssetClass")

class PortfolioReviewResponse(BaseModel):
    portfolio_id: str
    as_of_date: date
    overview: Optional[OverviewSection] = None
    allocation: Optional[AllocationSummary] = None
    performance: Optional[PerformanceResponse] = None
    risk_analytics: Optional[RiskResponse] = Field(None, alias="riskAnalytics")
    income_and_activity: Optional[Dict[str, IncomeSummary | ActivitySummary]] = Field(None, alias="incomeAndActivity")
    holdings: Optional[HoldingsSection] = None
    transactions: Optional[TransactionsSection] = None

    class Config:
        populate_by_name = True