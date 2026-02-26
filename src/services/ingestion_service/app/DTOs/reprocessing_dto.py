# src/services/ingestion_service/app/DTOs/reprocessing_dto.py
from typing import List

from pydantic import BaseModel, Field


class ReprocessingRequest(BaseModel):
    """
    Represents the request body for reprocessing a list of transactions.
    """

    transaction_ids: List[str] = Field(
        ...,
        min_length=1,
        description="A non-empty list of transaction_id strings to be reprocessed.",
    )
