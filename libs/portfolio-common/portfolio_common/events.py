from datetime import date, datetime # <-- IMPORT DATETIME
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal

class PortfolioEvent(BaseModel):
    """
    Event model for raw portfolio data.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    portfolio_id: str = Field(..., alias="portfolioId")
    base_currency: str = Field(..., alias="baseCurrency")
    open_date: date = Field(..., alias="openDate")
    close_date: Optional[date] = Field(None, alias="closeDate")
    risk_exposure: str = Field(..., alias="riskExposure")
    investment_time_horizon: str = Field(..., alias="investmentTimeHorizon")
    portfolio_type: str = Field(..., alias="portfolioType")
    objective: Optional[str] = None
    booking_center: str = Field(..., alias="bookingCenter")
    cif_id: str = Field(..., alias="cifId")
    is_leverage_allowed: bool = Field(False, alias="isLeverageAllowed")
    advisor_id: Optional[str] = Field(None, alias="advisorId")
    status: str

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
    model_config = ConfigDict(from_attributes=True)

    position_history_id: int = Field(..., alias="id")
    portfolio_id: str
    security_id: str
    position_date: date

# --- NEW CASHFLOW EVENT ---

class CashflowCalculatedEvent(BaseModel):
    """
    Event published after a cashflow has been calculated and persisted.
    """
    model_config = ConfigDict(from_attributes=True)

    cashflow_id: int = Field(..., alias="id")
    transaction_id: str
    portfolio_id: str
    security_id: Optional[str] = None
    cashflow_date: date
    amount: Decimal
    currency: str
    classification: str

# --- NEW TIME SERIES EVENTS ---

class PositionTimeseriesGeneratedEvent(BaseModel):
    """
    Event published after a position time series record has been generated.
    """
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    security_id: str
    date: date

class PortfolioTimeseriesGeneratedEvent(BaseModel):
    """
    Event published after a portfolio time series record has been generated.
    """
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    date: date