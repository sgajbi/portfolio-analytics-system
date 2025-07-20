# src/core/models/response.py

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from src.core.models.transaction import Transaction

class ErroredTransaction(BaseModel):
    """
    Represents a transaction that failed processing, along with the reason for failure.
    """
    transaction_id: str = Field(..., description="The ID of the transaction that failed.")
    error_reason: str = Field(..., description="The reason why the transaction processing failed.")

class TransactionProcessingResponse(BaseModel):
    """
    Represents the output response from the transaction processing API.
    """
    processed_transactions: List[Transaction] = Field(
        ...,
        description="List of transactions successfully processed, with calculated cost fields."
    )
    errored_transactions: List[ErroredTransaction] = Field(
        default_factory=list,
        description="List of transactions that failed validation or processing, with error reasons."
    )

    model_config = ConfigDict(
        json_schema_extra = {
             "example": {
                "processed_transactions": [],
                "errored_transactions": []
            }
        },
        extra='ignore'
    )