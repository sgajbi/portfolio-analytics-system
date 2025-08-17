# libs/portfolio-common/portfolio_common/database_models.py
from sqlalchemy import (
    Column, Integer, 
    String, Numeric, DateTime,
    Date, func,
    ForeignKey, UniqueConstraint, Boolean, JSON, Index
)
from sqlalchemy.orm import relationship

from .db_base import Base

class Portfolio(Base):
    __tablename__ = 'portfolios'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, unique=True, index=True, nullable=False)
    base_currency = Column(String(3), nullable=False)
    open_date = Column(Date, nullable=False)
    close_date = Column(Date, nullable=True)
    risk_exposure = Column(String, nullable=False)
    investment_time_horizon = Column(String, nullable=False)
    portfolio_type = Column(String, nullable=False)
    objective = Column(String, nullable=True)
    booking_center = Column(String, nullable=False)
    cif_id = Column(String, index=True, nullable=False)
    is_leverage_allowed = Column(Boolean, default=False, nullable=False)
    advisor_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class PositionHistory(Base):
    __tablename__ = 'position_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'), nullable=False)
    position_date = Column(Date, index=True, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    cost_basis = Column(Numeric(18, 10), nullable=False)
    cost_basis_local = Column(Numeric(18, 10), nullable=True) # --- NEW ---
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class DailyPositionSnapshot(Base):
    __tablename__ = 'daily_position_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    cost_basis = Column(Numeric(18, 10), nullable=False)
    cost_basis_local = Column(Numeric(18, 10), nullable=True) # --- NEW ---
    market_price = Column(Numeric(18, 10), nullable=True)
    market_value = Column(Numeric(18, 10), nullable=True)
    market_value_local = Column(Numeric(18, 10), nullable=True) # --- NEW ---
    unrealized_gain_loss = Column(Numeric(18, 10), nullable=True)
    unrealized_gain_loss_local = Column(Numeric(18, 10), nullable=True) # --- NEW ---
    valuation_status = Column(String, nullable=False, server_default='UNVALUED', index=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'security_id', 'date', name='_portfolio_security_date_uc'),
        Index('ix_daily_position_snapshots_covering', 'portfolio_id', 'security_id', date.desc(), id.desc()),
    )


class FxRate(Base):
    __tablename__ = 'fx_rates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='_currency_pair_date_uc'),)


class MarketPrice(Base):
    __tablename__ = 'market_prices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, index=True, nullable=False)
    price_date = Column(Date, nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint('security_id', 'price_date', name='_security_price_date_uc'),)


class Instrument(Base):
    __tablename__ = 'instruments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    isin = Column(String, unique=True, nullable=False)
    currency = Column(String, nullable=False)
    product_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), nullable=False)
    instrument_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    gross_transaction_amount = Column(Numeric(18, 10), nullable=False)
    trade_currency = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    settlement_date = Column(DateTime(timezone=True), nullable=True)
    trade_fee = Column(Numeric(18, 10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    gross_cost = Column(Numeric(18, 10), nullable=True)
    net_cost = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss = Column(Numeric(18, 10), nullable=True)
    # --- NEW COLUMNS ---
    transaction_fx_rate = Column(Numeric(18, 10), nullable=True)
    net_cost_local = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss_local = Column(Numeric(18, 10), nullable=True)

    costs = relationship("TransactionCost", back_populates="transaction", cascade="all, delete-orphan")
    cashflow = relationship("Cashflow", uselist=False, back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_transactions_portfolio_security', 'portfolio_id', 'security_id'),
    )



class TransactionCost(Base):
    __tablename__ = 'transaction_costs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'), nullable=False)
    fee_type = Column(String, nullable=False)
    amount = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    transaction = relationship("Transaction", back_populates="costs")

class Cashflow(Base):
    __tablename__ = 'cashflows'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'), nullable=False)
    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), index=True, nullable=False)
    security_id = Column(String, index=True, nullable=True)
    cashflow_date = Column(Date, index=True, nullable=False)
    amount = Column(Numeric(18, 10), nullable=False)
    currency = Column(String(3), nullable=False)
    classification = Column(String, nullable=False)
    timing = Column(String, nullable=False)
    level = Column(String, nullable=False)
    calculation_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    transaction = relationship("Transaction", back_populates="cashflow")

    __table_args__ = (UniqueConstraint('transaction_id', name='_transaction_id_uc'),)

class PositionTimeseries(Base):
    __tablename__ = 'position_timeseries'

    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), primary_key=True)
    security_id = Column(String, ForeignKey('instruments.security_id'), primary_key=True)
    date = Column(Date, primary_key=True)
    bod_market_value = Column(Numeric(18, 10), nullable=False)
    bod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_market_value = Column(Numeric(18, 10), nullable=False)
    fees = Column(Numeric(18, 10), default=0, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    cost = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class PortfolioTimeseries(Base):
    __tablename__ = 'portfolio_timeseries'

    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), primary_key=True)
    date = Column(Date, primary_key=True)
    bod_market_value = Column(Numeric(18, 10), nullable=False)
    bod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_cashflow = Column(Numeric(18, 10), nullable=False)
    eod_market_value = Column(Numeric(18, 10), nullable=False)
    fees = Column(Numeric(18, 10), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    service_name = Column(String, nullable=False)
    correlation_id = Column(String, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('event_id', 'service_name', name='_event_service_uc'),
    )

class OutboxEvent(Base):
    __tablename__ = 'outbox_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    aggregate_type = Column(String, nullable=False, index=True)
    aggregate_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    topic = Column(String, nullable=False)
    status = Column(String, default='PENDING', nullable=False, index=True)
    correlation_id = Column(String, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)


class PortfolioAggregationJob(Base):
    """
    Tracks portfolio-date pairs that require aggregation.
    This table acts as a stateful, idempotent queue to trigger portfolio time series calculations.
    """
    __tablename__ = 'portfolio_aggregation_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, nullable=False, index=True)
    aggregation_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default='PENDING', index=True)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'aggregation_date', name='_portfolio_date_uc'),
    )

class PortfolioValuationJob(Base):
    """
    Tracks portfolio-security-date combinations that require valuation.
    This table acts as a stateful, idempotent work set to trigger valuation calculations,
    preventing race conditions from multiple upstream events.
    """
    __tablename__ = 'portfolio_valuation_jobs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(String, nullable=False, index=True)
    security_id = Column(String, nullable=False, index=True)
    valuation_date = Column(Date, nullable=False, index=True)
    status = Column(String, nullable=False, default='PENDING', index=True)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'security_id', 'valuation_date', name='_portfolio_security_valuation_date_uc'),
    )

class DailyPerformanceMetric(Base):
    """
    Stores the fundamental daily performance metrics (linking factors) for a portfolio.
    This is the core persisted data for all on-the-fly TWR calculations.
    """
    __tablename__ = 'daily_performance_metrics'

    portfolio_id = Column(String, ForeignKey('portfolios.portfolio_id'), primary_key=True)
    date = Column(Date, primary_key=True, index=True)
    return_basis = Column(String, primary_key=True)  # 'NET' or 'GROSS'
    
    linking_factor = Column(Numeric(precision=28, scale=18), nullable=False)
    daily_return_pct = Column(Numeric(precision=28, scale=18), nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_daily_performance_metrics_portfolio_date_basis', 'portfolio_id', 'date', 'return_basis'),
    )