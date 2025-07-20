from datetime import date
from typing import Optional
from pydantic import BaseModel, Field

class TransactionEvent(BaseModel):
    """
    The shared event contract for a raw transaction that has been persisted
    and is ready for further processing by calculator services.
    """
    transaction_id: str
    portfolio_id: str
    instrument_id: str
    transaction_date: date
    transaction_type: str
    quantity: float
    price: float
    currency: str
    trade_fee: float = Field(default=0.0)
    settlement_date: Optional[date] = None