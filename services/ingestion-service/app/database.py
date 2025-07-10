
from sqlalchemy import create_engine, Column, String, Float, Date, DateTime, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from common.config import POSTGRES_URL

# Database setup
SQLALCHEMY_DATABASE_URL = POSTGRES_URL
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# SQLAlchemy models for our tables
class TransactionDB(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        PrimaryKeyConstraint('transaction_id', 'portfolio_id', 'instrument_id', 'transaction_date', name='pk_transactions'),
        # Add other constraints/indexes as needed later
    )

    transaction_id = Column(String, nullable=False)
    portfolio_id = Column(String, nullable=False)
    instrument_id = Column(String, nullable=False)
    transaction_date = Column(Date, nullable=False)
    transaction_type = Column(String, nullable=False) # BUY/SELL
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    trade_fee = Column(Float, default=0.0)
    settlement_date = Column(Date, nullable=True)
    created_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return (
            f"<TransactionDB(transaction_id='{self.transaction_id}', "
            f"portfolio_id='{self.portfolio_id}', instrument_id='{self.instrument_id}', "
            f"transaction_date='{self.transaction_date}')>"
        )