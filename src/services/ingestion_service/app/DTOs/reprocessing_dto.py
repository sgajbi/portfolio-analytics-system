# src/services/ingestion_service/app/DTOs/reprocessing_dto.py
from pydantic import BaseModel, Field
from typing import List

class ReprocessingRequest(BaseModel):
    """
    Represents the request body for reprocessing a list of transactions.
    """
    transaction_ids: List[str] = Field(..., description="A list of transaction_id strings to be reprocessed.")