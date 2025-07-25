# libs/portfolio-common/portfolio_common/database_models.py
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Date, func, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

# Use the modern declarative_base from sqlalchemy.orm
Base = declarative_base()

class MarketPrice(Base):
    __tablename__ = 'market_prices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, index=True, nullable=False)
    price_date = Column(Date, nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint('security_id', 'price_date', name='_security_price_date_uc'),)


class Instrument(Base):
    __tablename__ = 'instruments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    security_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    isin = Column(String, unique=True, nullable=False)
    currency = Column(String, nullable=False)
    product_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    portfolio_id = Column(String, nullable=False)
    instrument_id = Column(String, nullable=False)
    security_id = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    gross_transaction_amount = Column(Numeric(18, 10), nullable=False)
    trade_currency = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(DateTime, nullable=False)
    settlement_date = Column(DateTime, nullable=True)
    trade_fee = Column(Numeric(18, 10), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    gross_cost = Column(Numeric(18, 10), nullable=True)
    net_cost = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss = Column(Numeric(18, 10), nullable=True)

    costs = relationship("TransactionCost", back_populates="transaction", cascade="all, delete-orphan")

class TransactionCost(Base):
    __tablename__ = 'transaction_costs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'), nullable=False)
    fee_type = Column(String, nullable=False)
    amount = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    transaction = relationship("Transaction", back_populates="costs")