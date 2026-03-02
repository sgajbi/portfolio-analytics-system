# services/ingestion_service/app/DTOs/business_date_dto.py
from datetime import date
from typing import List
from pydantic import BaseModel, Field


class BusinessDate(BaseModel):
    """
    Represents a single business date for ingestion.
    """
    business_date: date = Field(..., description="A valid business date.")
    calendar_code: str = Field(
        default="GLOBAL",
        description="Business calendar identifier (for example: GLOBAL, SIX_CH, NYSE_US).",
    )
    market_code: str | None = Field(
        default=None,
        description="Optional market or venue code associated with the business date.",
    )
    source_system: str | None = Field(
        default=None,
        description="Optional upstream source system identifier for lineage.",
    )
    source_batch_id: str | None = Field(
        default=None,
        description="Optional upstream batch identifier for lineage and replay tracking.",
    )


class BusinessDateIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of business dates.
    """
    business_dates: List[BusinessDate]
