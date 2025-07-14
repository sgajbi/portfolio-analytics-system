from sqlalchemy import Column, String, Float, Date, DateTime, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
import uuid
from common.db import Base # Import Base from common.db

# The Transaction model based on your uploaded database_models.py
class Transaction(Base):
    __tablename__ = 'transactions'

    transaction_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    instrument_id = Column(String, nullable=False)
    transaction_date = Column(Date, nullable=False) # Date of the transaction
    transaction_type = Column(String, nullable=False) # e.g., 'BUY', 'SELL'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    trade_fee = Column(Float, nullable=False)
    settlement_date = Column(Date, nullable=False) # Date of settlement
    created_at = Column(DateTime, default=datetime.utcnow) # Timestamp of record creation

    # Define a composite primary key as per the uploaded file
    __table_args__ = (
        PrimaryKeyConstraint('transaction_id', 'portfolio_id', 'instrument_id', 'transaction_date', name='pk_transactions'),
        {}
    )

    def __repr__(self):
        return (f"<Transaction("
                f"transaction_id='{self.transaction_id}', "
                f"portfolio_id='{self.portfolio_id}', "
                f"instrument_id='{self.instrument_id}', "
                f"transaction_date='{self.transaction_date}')>")

# New model for TransactionCost
class TransactionCost(Base):
    __tablename__ = 'transaction_costs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    # Link to Transaction using its business key fields for lookup
    transaction_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=False, index=True)
    instrument_id = Column(String, nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True) # Ensure this matches the type in Transaction
    
    cost_amount = Column(Float, nullable=False)
    cost_currency = Column(String, nullable=False)
    calculation_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return (f"<TransactionCost("
                f"id='{self.id}', "
                f"transaction_id='{self.transaction_id}', "
                f"cost_amount={self.cost_amount})>")