from datetime import date, datetime
from pydantic import BaseModel, Field

class TransactionEvent(BaseModel):
    transaction_id: str = Field(..., description="Unique identifier for the transaction")
    portfolio_id: str = Field(..., description="Identifier for the portfolio involved")
    instrument_id: str = Field(..., description="Identifier for the instrument traded (e.g., stock ticker)")
    transaction_date: date = Field(..., description="Date when the transaction occurred (YYYY-MM-DD)")
    transaction_type: str = Field(..., description="Type of transaction (e.g., BUY, SELL)")
    quantity: float = Field(..., gt=0, description="Quantity of the instrument traded, must be positive")
    price: float = Field(..., gt=0, description="Price per unit of the instrument, must be positive")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency of the transaction (e.g., USD, EUR)")
    trade_fee: float = Field(default=0.0, ge=0, description="Any fees associated with the trade, non-negative")
    settlement_date: date = Field(..., description="Date when the transaction is settled (YYYY-MM-DD)")
    # created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when the event was created")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "transaction_id": "TRN001",
                    "portfolio_id": "PORT001",
                    "instrument_id": "AAPL",
                    "transaction_date": "2023-01-15",
                    "transaction_type": "BUY",
                    "quantity": 10.0,
                    "price": 150.0,
                    "currency": "USD",
                    "trade_fee": 1.5,
                    "settlement_date": "2023-01-17"
                },
                {
                    "transaction_id": "TRN002",
                    "portfolio_id": "PORT001",
                    "instrument_id": "GOOG",
                    "transaction_date": "2023-02-20",
                    "transaction_type": "SELL",
                    "quantity": 5.0,
                    "price": 2500.0,
                    "currency": "USD",
                    "trade_fee": 2.0,
                    "settlement_date": "2023-02-22"
                }
            ]
        }
    }