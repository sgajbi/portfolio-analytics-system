# libs/portfolio-common/portfolio_common/events.py
from datetime import date, datetime
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
    transaction_date: datetime
    transaction_type: str
    quantity: Decimal
    price: Decimal
    gross_transaction_amount: Decimal
    trade_currency: str
    currency: str
    trade_fee: Decimal = Field(default=Decimal(0))
    settlement_date: Optional[datetime] = None
    net_cost: Optional[Decimal] = None
    gross_cost: Optional[Decimal] = None
    realized_gain_loss: Optional[Decimal] = None
    
    # --- NEW FIELDS ---
    transaction_fx_rate: Optional[Decimal] = None
    net_cost_local: Optional[Decimal] = None
    realized_gain_loss_local: Optional[Decimal] = None

class PositionHistoryPersistedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: str
    security_id: str
    position_date: date

class DailyPositionSnapshotPersistedEvent(BaseModel):
    """
    Event published after a daily position snapshot has been created or updated.
    This is the definitive trigger for time series generation.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    portfolio_id: str
    security_id: str
    date: date

class CashflowCalculatedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cashflow_id: int = Field(..., alias="id")
    transaction_id: str
    portfolio_id: str
    security_id: Optional[str] = None
    cashflow_date: date
    amount: Decimal
    currency: str
    classification: str

class PositionTimeseriesGeneratedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    security_id: str
    date: date

class PortfolioTimeseriesGeneratedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    portfolio_id: str
    date: date

class PortfolioAggregationRequiredEvent(BaseModel):
    """
    Event published by the AggregationScheduler to trigger a portfolio
    time series calculation for a specific portfolio and date.
    """
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str
    aggregation_date: date
    correlation_id: Optional[str] = None

class PortfolioValuationRequiredEvent(BaseModel):
    """
    Event published by the ValuationScheduler to trigger a position valuation
    for a specific portfolio, security, and date.
    """
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str
    security_id: str
    valuation_date: date
    correlation_id: Optional[str] = None