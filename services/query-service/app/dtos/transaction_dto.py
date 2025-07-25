from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from datetime import datetime
from typing import List, Optional

class TransactionRecord(BaseModel):
    """
    Represents a single, detailed transaction record for API responses.
    """
    transaction_id: str
    transaction_date: datetime
    transaction_type: str
    security_id: str
    quantity: Decimal
    price: Decimal
    gross_transaction_amount: Decimal
    net_cost: Optional[Decimal] = None
    realized_gain_loss: Optional[Decimal] = None
    currency: str
    
    model_config = ConfigDict(
        from_attributes=True
    )

class PaginatedTransactionResponse(BaseModel):
    """
    Represents the paginated API response for a transaction query.
    """
    portfolio_id: str = Field(..., description="The ID of the portfolio.")
    total: int = Field(..., description="The total number of transactions matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    transactions: List[TransactionRecord] = Field(..., description="The list of transaction records for the current page.")