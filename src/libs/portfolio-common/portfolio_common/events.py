# libs/portfolio-common/portfolio_common/events.py
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal

class BusinessDateEvent(BaseModel):
    """Event model for a raw business date."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    business_date: date = Field(..., alias="businessDate")

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

class MarketPricePersistedEvent(BaseModel):
    """
    Event published after a market price has been successfully persisted.
    """
    model_config = ConfigDict(from_attributes=True)
    
    security_id: str
    price_date: date
    price: Decimal
    currency: str

class InstrumentEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    security_id: str = Field(..., alias="securityId")
    name: str
    isin: str
    currency: str = Field(..., alias="instrumentCurrency")
    product_type: str = Field(..., alias="productType")
    asset_class: Optional[str] = Field(None, alias="assetClass")
    sector: Optional[str] = None
    country_of_risk: Optional[str] = Field(None, alias="countryOfRisk")
    rating: Optional[str] = None
    maturity_date: Optional[date] = Field(None, alias="maturityDate")
    issuer_id: Optional[str] = Field(None, alias="issuerId")
    ultimate_parent_issuer_id: Optional[str] = Field(None, alias="ultimateParentIssuerId")

class TransactionEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

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
    trade_fee: Optional[Decimal] = Field(default=Decimal(0))
    settlement_date: Optional[datetime] = None
    net_cost: Optional[Decimal] = None
    gross_cost: Optional[Decimal] = None
    realized_gain_loss: Optional[Decimal] = None
    transaction_fx_rate: Optional[Decimal] = None
    net_cost_local: Optional[Decimal] = None
    realized_gain_loss_local: Optional[Decimal] = None
    epoch: Optional[int] = None

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
    epoch: int

class CashflowCalculatedEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    cashflow_id: int = Field(..., alias="id")
    transaction_id: str
    portfolio_id: str
    security_id: Optional[str] = None
    cashflow_date: date
    epoch: Optional[int] = None
    amount: Decimal
    currency: str
    classification: str
    timing: str
    is_position_flow: bool
    is_portfolio_flow: bool
    calculation_type: str = Field(..., alias="calculationType")

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
    epoch: int
    correlation_id: Optional[str] = None

class PerformanceCalculatedEvent(BaseModel):
    """
    Event published after daily performance metrics (Net and Gross)
    have been calculated and persisted for a given portfolio and date.
    """
    model_config = ConfigDict(from_attributes=True)

    portfolio_id: str
    date: date