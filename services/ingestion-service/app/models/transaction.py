from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

class Transaction(BaseModel):
    transaction_id: str = Field(..., example="TRN001")
    portfolio_id: str = Field(..., example="PORT001")
    instrument_id: str = Field(..., example="AAPL")
    security_id: str = Field(..., example="SEC_AAPL")
    transaction_date: date = Field(..., example="2023-01-15")
    transaction_type: str = Field(..., example="BUY")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    gross_transaction_amount: float = Field(..., gt=0)
    trade_currency: str = Field(..., example="USD")
    currency: str = Field(..., example="USD")
    trade_fee: Optional[float] = Field(default=0.0, ge=0)
    settlement_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)