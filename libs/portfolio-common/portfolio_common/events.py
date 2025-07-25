from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class InstrumentEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    security_id: str = Field(..., alias="securityId")
    name: str
    isin: str
    currency: str = Field(..., alias="instrumentCurrency")
    product_type: str = Field(..., alias="productType")

class TransactionEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    portfolio_id: str
    instrument_id: str
    security_id: str
    transaction_date: date
    transaction_type: str
    quantity: float
    price: float
    gross_transaction_amount: float
    trade_currency: str
    currency: str
    trade_fee: float = Field(default=0.0)
    settlement_date: Optional[date] = None