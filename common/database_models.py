from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, unique=True, index=True, nullable=False)
    portfolio_id = Column(String, nullable=False)
    asset_id = Column(String, nullable=False) # Ingestion service uses 'instrument_id', this should be harmonized later
    transaction_type = Column(String, nullable=False)
    quantity = Column(Numeric(18, 10), nullable=False)
    price = Column(Numeric(18, 10), nullable=False)
    currency = Column(String, nullable=False)
    transaction_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # --- NEW COLUMNS TO STORE CALCULATION RESULTS ---
    gross_cost = Column(Numeric(18, 10), nullable=True)
    net_cost = Column(Numeric(18, 10), nullable=True)
    realized_gain_loss = Column(Numeric(18, 10), nullable=True)
    # --- END NEW COLUMNS ---

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