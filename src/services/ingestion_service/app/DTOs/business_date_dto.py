# services/ingestion_service/app/DTOs/business_date_dto.py
from datetime import date
from typing import List
from pydantic import BaseModel, Field


class BusinessDate(BaseModel):
    """
    Represents a single business date for ingestion.
    """
    business_date: date = Field(..., alias="businessDate", description="A valid business date.")


class BusinessDateIngestionRequest(BaseModel):
    """
    Represents the request body for ingesting a list of business dates.
    """
    business_dates: List[BusinessDate]