# src/core/models/request.py

import logging
from pydantic import BaseModel, Field, ConfigDict # NEW: Import ConfigDict
# No direct import of Transaction needed here, as it uses list[dict]

logger = logging.getLogger(__name__)

class TransactionProcessingRequest(BaseModel):
    """
    Represents the input payload for the transaction processing API.
    """
    # FIX: Changed list[Transaction] to list[dict]
    existing_transactions: list[dict] = Field(
        default_factory=list,
        description="List of previously processed transactions (raw dictionaries) with cost fields already computed."
    )
    # FIX: Changed list[Transaction] to list[dict]
    new_transactions: list[dict] = Field(
        ...,
        description="New transactions to be processed (raw dictionaries, including possible backdated ones)."
    )

    # Replaced class Config with model_config
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "existing_transactions": [
                    {
                        "transaction_id": "existing_buy_001",
                        "portfolio_id": "PORT001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "BUY",
                        "transaction_date": "2023-01-01T00:00:00Z", # Ensure datetime format
                        "settlement_date": "2023-01-03T00:00:00Z", # Ensure datetime format
                        "quantity": 10.0,
                        "gross_transaction_amount": 1500.0,
                        "net_transaction_amount": 1505.5,
                        "fees": {"brokerage": 5.5},
                        "accrued_interest": 0.0,
                        "average_price": 150.0,
                        "trade_currency": "USD",
                        "net_cost": 1505.5,
                        "gross_cost": 1500.0,
                        "realized_gain_loss": None
                    }
                ],
                "new_transactions": [
                    {
                        "transaction_id": "new_buy_001",
                        "portfolio_id": "PORT001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "BUY",
                        "transaction_date": "2023-01-10T00:00:00Z",
                        "settlement_date": "2023-01-12T00:00:00Z",
                        "quantity": 5.0,
                        "gross_transaction_amount": 760.0,
                        "fees": {"brokerage": 2.0},
                        "trade_currency": "USD"
                    },
                    {
                        "transaction_id": "new_sell_001",
                        "portfolio_id": "PORT001",
                        "instrument_id": "AAPL",
                        "security_id": "SEC001",
                        "transaction_type": "SELL",
                        "transaction_date": "2023-01-15T00:00:00Z",
                        "settlement_date": "2023-01-17T00:00:00Z",
                        "quantity": 8.0,
                        "gross_transaction_amount": 1250.0,
                        "fees": {"brokerage": 3.0},
                        "trade_currency": "USD"
                    },
                    {
                        "transaction_id": "invalid_sell_001",
                        "portfolio_id": "PORT001",
                        "instrument_id": "MSFT",
                        "security_id": "SEC002",
                        "transaction_type": "SELL",
                        "transaction_date": "2023-01-18T00:00:00Z",
                        "settlement_date": "2023-01-20T00:00:00Z",
                        "quantity": 100.0,
                        "gross_transaction_amount": 10000.0,
                        "fees": {"brokerage": 10.0},
                        "trade_currency": "USD"
                    }
                ]
            }
        },
        extra='ignore' # Added for robustness, ignore extra fields in input
    )