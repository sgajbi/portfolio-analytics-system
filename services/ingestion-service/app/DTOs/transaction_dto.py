# services/ingestion-service/app/DTOs/transaction_dto.py
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field, condecimal # Import condecimal
from decimal import Decimal # Import Decimal

class Transaction(BaseModel):
    transaction_id: str = Field(json_schema_extra={'example': 'TRN001'})
    portfolio_id: str = Field(json_schema_extra={'example': 'PORT001'})
    security_id: str = Field(json_schema_extra={'example': 'SEC_AAPL'})
    transaction_date: datetime = Field(json_schema_extra={'example': '2023-01-15T10:00:00Z'})
    transaction_type: str = Field(json_schema_extra={'example': 'BUY'})
    quantity: condecimal(gt=Decimal(0)) = Field(json_schema_extra={'example': '10.0'})
    price: condecimal(gt=Decimal(0)) = Field(json_schema_extra={'example': '150.0'})
    gross_transaction_amount: condecimal(gt=Decimal(0)) = Field(json_schema_extra={'example': '1500.0'})
    trade_currency: str = Field(json_schema_extra={'example': 'USD'})
    currency: str = Field(json_schema_extra={'example': 'USD'})
    trade_fee: Optional[condecimal(ge=Decimal(0))] = Field(default=Decimal(0), json_schema_extra={'example': '5.0'})
    settlement_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TransactionIngestionRequest(BaseModel):
    transactions: List[Transaction]