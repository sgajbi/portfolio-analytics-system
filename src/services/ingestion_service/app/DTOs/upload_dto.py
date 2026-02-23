from typing import Any, Literal

from pydantic import BaseModel, Field


UploadEntityType = Literal[
    "portfolios",
    "instruments",
    "transactions",
    "market_prices",
    "fx_rates",
    "business_dates",
]


class UploadRowError(BaseModel):
    row_number: int = Field(..., description="1-based row number from the uploaded file.")
    message: str = Field(..., description="Validation error message for the row.")


class UploadPreviewResponse(BaseModel):
    entity_type: UploadEntityType
    file_format: Literal["csv", "xlsx"]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    sample_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Normalized and validated sample rows for UI preview.",
    )
    errors: list[UploadRowError] = Field(
        default_factory=list,
        description="Validation errors by row for correction before commit.",
    )


class UploadCommitResponse(BaseModel):
    entity_type: UploadEntityType
    file_format: Literal["csv", "xlsx"]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    published_rows: int
    skipped_rows: int
    message: str
