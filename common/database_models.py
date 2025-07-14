
from sqlalchemy import Column, String, Float, Date, DateTime, func, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

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

    # Define a composite primary key
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