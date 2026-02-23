from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from .portfolio_dto import PortfolioRecord
from .review_dto import PortfolioReviewResponse, ReviewSection


class PortfolioCoreSnapshotRequest(BaseModel):
    as_of_date: date = Field(
        ...,
        alias="asOfDate",
        description="Business date for which the PAS snapshot should be generated.",
        json_schema_extra={"example": "2026-02-23"},
    )
    include_sections: List[ReviewSection] = Field(
        default_factory=lambda: [
            ReviewSection.OVERVIEW,
            ReviewSection.ALLOCATION,
            ReviewSection.INCOME_AND_ACTIVITY,
            ReviewSection.HOLDINGS,
            ReviewSection.TRANSACTIONS,
        ],
        alias="includeSections",
        description="Review sections to include in the snapshot payload.",
    )
    consumer_system: Optional[str] = Field(
        None,
        alias="consumerSystem",
        description="Optional caller system identifier (for audit/integration tracing).",
        json_schema_extra={"example": "PA"},
    )

    model_config = {
        "populate_by_name": True,
    }


class PortfolioCoreSnapshotResponse(BaseModel):
    contract_version: str = Field(
        "v1",
        alias="contractVersion",
        description="Version of the integration contract schema.",
        json_schema_extra={"example": "v1"},
    )
    consumer_system: Optional[str] = Field(
        None,
        alias="consumerSystem",
        description="Echoed consumer system identifier from request.",
    )
    portfolio: PortfolioRecord = Field(
        ...,
        description="Canonical PAS portfolio record (system-of-record view).",
    )
    snapshot: PortfolioReviewResponse = Field(
        ...,
        description="As-of snapshot payload assembled from PAS query capabilities.",
    )

    model_config = {
        "populate_by_name": True,
    }
