from datetime import date, datetime
from typing import List, Literal, Optional

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
    metadata: "PortfolioCoreSnapshotMetadata" = Field(
        ...,
        description="Provenance, freshness, lineage, and section-governance metadata.",
    )

    model_config = {
        "populate_by_name": True,
    }


FreshnessStatus = Literal["FRESH", "STALE", "UNKNOWN"]


class CoreSnapshotLineageRefs(BaseModel):
    portfolio_id: str = Field(..., alias="portfolioId")
    as_of_date: date = Field(..., alias="asOfDate")
    correlation_id: Optional[str] = Field(None, alias="correlationId")

    model_config = {"populate_by_name": True}


class SectionGovernanceMetadata(BaseModel):
    requested_sections: List[ReviewSection] = Field(..., alias="requestedSections")
    effective_sections: List[ReviewSection] = Field(..., alias="effectiveSections")
    dropped_sections: List[ReviewSection] = Field(default_factory=list, alias="droppedSections")
    warnings: List[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PortfolioCoreSnapshotMetadata(BaseModel):
    generated_at: datetime = Field(..., alias="generatedAt")
    source_as_of_date: date = Field(..., alias="sourceAsOfDate")
    freshness_status: FreshnessStatus = Field(..., alias="freshnessStatus")
    lineage_refs: CoreSnapshotLineageRefs = Field(..., alias="lineageRefs")
    section_governance: SectionGovernanceMetadata = Field(..., alias="sectionGovernance")

    model_config = {"populate_by_name": True}


PortfolioCoreSnapshotResponse.model_rebuild()
