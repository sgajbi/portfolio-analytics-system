from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class SupportOverviewResponse(BaseModel):
    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    current_epoch: Optional[int] = Field(
        None,
        description="Current active epoch for the portfolio across position state keys.",
        examples=[3],
    )
    active_reprocessing_keys: int = Field(
        ...,
        description="Number of portfolio-security keys currently marked REPROCESSING.",
        examples=[2],
    )
    pending_valuation_jobs: int = Field(
        ...,
        description="Number of pending/processing valuation jobs for the portfolio.",
        examples=[14],
    )
    pending_aggregation_jobs: int = Field(
        ...,
        description="Number of pending/processing portfolio aggregation jobs for the portfolio.",
        examples=[1],
    )
    latest_transaction_date: Optional[date] = Field(
        None,
        description="Most recent transaction business date observed for the portfolio.",
        examples=["2025-12-30"],
    )
    latest_position_snapshot_date: Optional[date] = Field(
        None,
        description="Most recent daily position snapshot date in the current epoch.",
        examples=["2025-12-30"],
    )


class LineageResponse(BaseModel):
    portfolio_id: str = Field(..., description="Unique portfolio identifier.", examples=["PF-001"])
    security_id: str = Field(..., description="Unique security identifier.", examples=["AAPL.OQ"])
    epoch: int = Field(..., description="Current active epoch for this key.", examples=[3])
    watermark_date: date = Field(
        ...,
        description="Watermark date from which replay/reprocessing is active.",
        examples=["2025-11-01"],
    )
    reprocessing_status: str = Field(
        ..., description="Current status for this key.", examples=["CURRENT", "REPROCESSING"]
    )
    latest_position_history_date: Optional[date] = Field(
        None,
        description="Latest date available in position_history for current epoch.",
        examples=["2025-12-30"],
    )
    latest_daily_snapshot_date: Optional[date] = Field(
        None,
        description="Latest date available in daily_position_snapshots for current epoch.",
        examples=["2025-12-30"],
    )
    latest_valuation_job_date: Optional[date] = Field(
        None,
        description="Latest valuation job business date for current epoch.",
        examples=["2025-12-30"],
    )
    latest_valuation_job_status: Optional[str] = Field(
        None,
        description="Status of the latest valuation job for current epoch.",
        examples=["PENDING", "PROCESSING", "DONE", "FAILED"],
    )
