# src/core/models/response.py

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict # NEW: Import ConfigDict
from app.cost_engine.core.models.transaction import Transaction # Adjusted import

class ErroredTransaction(BaseModel):
    """
    Represents a transaction that failed processing, along with the reason for failure.
    """
    transaction_id: str = Field(..., description="The ID of the transaction that failed.")
    error_reason: str = Field(..., description="The reason why the transaction processing failed.")
    # You might consider adding an error_code (from an Enum) here for programmatic handling
    # error_code: Optional[ErrorCode] = None

class TransactionProcessingResponse(BaseModel):
    """
    Represents the output response from the transaction processing API.
    """
    processed_transactions: List[Transaction] = Field(
        ...,
        description="List of transactions successfully processed, with calculated cost fields."
    )
    errored_transactions: List[ErroredTransaction] = Field(
        default_factory=list,
        description="List of transactions that failed validation or processing, with error reasons."
    )

    # Replaced class Config with model_config
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "processed_transactions": [
                    {
                        "transaction_id": "new_buy_001",
                        "portfolioId": "PORT001",
                        "instrumentId": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "BUY",
                        "transaction_date": "2023-01-10",
                        "settlement_date": "2023-01-12",
                        "quantity": 5.0,
                        "gross_transaction_amount": 760.0,
                        "fees": {"brokerage": 2.0},
                        "accrued_interest": 0.0,
                        "average_price": 0.0,
                        "tradeCurrency": "USD",
                        "net_cost": 762.0,
                        "gross_cost": 760.0,
                        "realized_gain_loss": None
                    },
                    {
                        "transaction_id": "new_sell_001",
                        "portfolioId": "PORT001",
                        "instrumentId": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "SELL",
                        "transaction_date": "2023-01-15",
                        "settlement_date": "2023-01-17",
                        "quantity": 8.0,
                        "gross_transaction_amount": 1250.0,
                        "fees": {"brokerage": 3.0},
                        "accrued_interest": 0.0,
                        "average_price": 0.0,
                        "tradeCurrency": "USD",
                        "net_cost": None,
                        "gross_cost": None,
                        "realized_gain_loss": 50.0
                    }
                ],
                "errored_transactions": [
                    {
                        "transaction_id": "invalid_sell_001",
                        "error_reason": "Sell quantity exceeds available holdings for MSFT (SEC002)"
                    }
                ]
            }
        },
        extra='ignore'
    )