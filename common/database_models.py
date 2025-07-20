# common/database_models.py

from sqlalchemy import Column, Integer, String, DateTime, Numeric, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint

Base = declarative_base()

class Transaction(Base):
    """SQLAlchemy ORM model for financial transactions."""
    __tablename__ = 'transactions'
    __table_args__ = (UniqueConstraint('portfolio_id', 'transaction_id', name='_portfolio_transaction_uc'),)

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, index=True, nullable=False)
    portfolio_id = Column(String, index=True, nullable=False)
    instrument_id = Column(String, index=True, nullable=False)
    security_id = Column(String, index=True, nullable=False)
    transaction_type = Column(String, nullable=False)
    transaction_date = Column(DateTime, nullable=False)
    settlement_date = Column(DateTime, nullable=False)
    quantity = Column(Numeric(precision=18, scale=10), nullable=False)
    gross_transaction_amount = Column(Numeric(precision=18, scale=10), nullable=False)
    net_transaction_amount = Column(Numeric(precision=18, scale=10), nullable=True)
    fees = Column(JSON, nullable=True)
    accrued_interest = Column(Numeric(precision=18, scale=10), default=0.0)
    average_price = Column(Numeric(precision=18, scale=10), nullable=True)
    trade_currency = Column(String, nullable=False)
    # NEW: Columns for calculated costs from transaction-cost-engine
    net_cost = Column(Numeric(precision=18, scale=10), nullable=True)
    gross_cost = Column(Numeric(precision=18, scale=10), nullable=True)
    realized_gain_loss = Column(Numeric(precision=18, scale=10), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())

    # Relationship to TransactionCost (if you decide to keep it separate for fees)
    transaction_costs = relationship("TransactionCost", back_populates="transaction", cascade="all, delete-orphan")

class TransactionCost(Base):
    """SQLAlchemy ORM model for storing detailed transaction costs (e.g., fees)."""
    __tablename__ = 'transaction_costs'

    id = Column(Integer, primary_key=True, index=True)
    # Changed to ForeignKey to link with the 'transactions' table's 'id' column
    transaction_id = Column(String, ForeignKey('transactions.transaction_id'), nullable=False, index=True) # Ensure this points to the unique ID of the transaction
    fee_type = Column(String, nullable=False)
    amount = Column(Numeric(precision=18, scale=10), nullable=False)
    currency = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now(), server_default=func.now())

    # Define relationship back to Transaction
    transaction = relationship("Transaction", back_populates="transaction_costs",
                               primaryjoin="TransactionCost.transaction_id == Transaction.transaction_id",
                               foreign_keys=[transaction_id])