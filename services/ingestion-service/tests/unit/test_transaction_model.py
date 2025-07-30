import pytest
from datetime import date, datetime
from pydantic import ValidationError

from app.DTOs.transaction_dto import Transaction

def test_transaction_model_success():
    """
    Tests that the Transaction model successfully validates a correct data payload.
    """
    valid_payload = {
        "transaction_id": "test_txn_001",
        "portfolio_id": "test_port_001",
        "instrument_id": "AAPL",
        "security_id": "SEC_AAPL",
        "transaction_date": "2025-07-21T00:00:00",
        "transaction_type": "BUY",
        "quantity": 10.0,
        "price": 150.0,
        "gross_transaction_amount": 1500.0,
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": 5.0,
        "settlement_date": "2025-07-23T00:00:00",
        "created_at": datetime.now()
    }

    # This should not raise an exception
    transaction = Transaction(**valid_payload)

    assert transaction.transaction_id == "test_txn_001"
    assert transaction.quantity == 10.0
    assert transaction.transaction_date == datetime(2025, 7, 21, 0, 0)

def test_transaction_model_missing_field_fails():
    """
    Tests that the Transaction model fails validation if a required field is missing.
    """
    invalid_payload = {
        "transaction_id": "test_txn_002",
        "portfolio_id": "test_port_002",
        # instrument_id is missing
        "security_id": "SEC_GOOG",
        "transaction_date": "2025-07-22T00:00:00",
        "transaction_type": "SELL",
        "quantity": 5.0,
        "price": 200.0,
        "gross_transaction_amount": 1000.0,
        "trade_currency": "USD",
        "currency": "USD"
    }

    with pytest.raises(ValidationError):
        Transaction(**invalid_payload)