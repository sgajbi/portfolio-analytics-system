from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field

class TransactionEvent(BaseModel):
    transaction_id: str
    portfolio_id: str
    instrument_id: str
    transaction_date: date # Match SQLAlchemy Date type
    transaction_type: str
    quantity: float # Match SQLAlchemy Float type
    price: float # Match SQLAlchemy Float type
    currency: str
    trade_fee: float # New field from updated Transaction model
    settlement_date: date # New field from updated Transaction model

class TransactionCostCalculatedEvent(BaseModel):
    transaction_id: str
    portfolio_id: str
    instrument_id: str
    transaction_date: date # Link to the specific transaction
    cost_amount: float
    cost_currency: str
    calculation_date: datetime = Field(default_factory=datetime.utcnow)

# Define Kafka topics for clarity and centralized management
KAFKA_RAW_TRANSACTIONS_TOPIC = "raw_transactions"
KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC = "raw_transactions_completed" # Topic consumed by this service
KAFKA_CALCULATED_TRANSACTIONS_TOPIC = "calculated_transactions" # Topic produced by this service