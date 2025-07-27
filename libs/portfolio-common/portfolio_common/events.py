from datetime import date, datetime # <-- IMPORT DATETIME
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal

class FxRateEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    from_currency: str = Field(..., alias="fromCurrency")
    to_currency: str = Field(..., alias="toCurrency")
    rate_date: date = Field(..., alias="rateDate")
    rate: Decimal

class MarketPriceEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    security_id: str = Field(..., alias="securityId")
    price_date: date = Field(..., alias="priceDate")
    price: Decimal
    currency: str

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
    transaction_date: datetime # <-- CORRECTED TYPE
    transaction_type: str
    quantity: Decimal
    price: Decimal
    gross_transaction_amount: Decimal
    trade_currency: str
    currency: str
    trade_fee: Decimal = Field(default=Decimal(0))
    settlement_date: Optional[datetime] = None # <-- CORRECTED TYPE
    net_cost: Optional[Decimal] = None
    realized_gain_loss: Optional[Decimal] = None

# --- NEW POSITION EVENTS ---

class PositionHistoryEvent(BaseModel):
    """
    Represents a full, valued position history record.
    This can be used for publishing 'position_valued' events.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    portfolio_id: str
    security_id: str
    transaction_id: str
    position_date: date
    quantity: Decimal
    cost_basis: Decimal
    market_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_gain_loss: Optional[Decimal] = None

class PositionHistoryPersistedEvent(BaseModel):
    """
A lightweight event published when a new position history record is created.
    This triggers the valuation service.
    """
    model_config = ConfigDict(from_attributes=True)

    position_history_id: int = Field(..., alias="id")
    portfolio_id: str
    security_id: str
    position_date: date