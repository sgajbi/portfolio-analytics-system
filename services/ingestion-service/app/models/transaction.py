from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

class Transaction(BaseModel):
    transaction_id: str = Field(..., example="TRN001")
    portfolio_id: str = Field(..., example="PORT001")
    instrument_id: str = Field(..., example="AAPL")
    transaction_date: date = Field(..., example="2023-01-15")
    transaction_type: str = Field(..., example="BUY", pattern="^(BUY|SELL)$")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    currency: str = Field(..., example="USD", min_length=3, max_length=3)
    trade_fee: Optional[float] = Field(default=0.0, ge=0)
    settlement_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "TRN001",
                "portfolio_id": "PORT001",
                "instrument_id": "AAPL",
                "transaction_date": "2023-01-15",
                "transaction_type": "BUY",
                "quantity": 10.0,
                "price": 150.0,
                "currency": "USD",
                "trade_fee": 1.50,
                "settlement_date": "2023-01-17"
            }
        }