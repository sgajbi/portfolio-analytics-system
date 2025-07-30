# services/ingestion-service/app/DTOs/transaction_dto.py
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, condecimal # Import condecimal
from decimal import Decimal # Import Decimal

class Transaction(BaseModel):
    transaction_id: str = Field(..., example="TRN001")
    portfolio_id: str = Field(..., example="PORT001")
    instrument_id: str = Field(..., example="AAPL")
    security_id: str = Field(..., example="SEC_AAPL")
    transaction_date: datetime = Field(..., example="2023-01-15T10:00:00Z")
    transaction_type: str = Field(..., example="BUY")
    quantity: condecimal(gt=Decimal(0)) = Field(..., example="10.0") # Changed to condecimal
    price: condecimal(gt=Decimal(0)) = Field(..., example="150.0") # Changed to condecimal
    gross_transaction_amount: condecimal(gt=Decimal(0)) = Field(..., example="1500.0") # Changed to condecimal
    trade_currency: str = Field(..., example="USD")
    currency: str = Field(..., example="USD")
    trade_fee: Optional[condecimal(ge=Decimal(0))] = Field(default=Decimal(0), example="5.0") # Changed to condecimal and default Decimal
    settlement_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction]