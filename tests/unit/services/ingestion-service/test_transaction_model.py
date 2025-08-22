import pytest
from datetime import date, datetime
from pydantic import ValidationError
from decimal import Decimal

from services.ingestion_service.app.DTOs.transaction_dto import Transaction

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
        "quantity": "10.0",
        "price": "150.0",
        "gross_transaction_amount": "1500.0",
        "trade_currency": "USD",
        "currency": "USD",
        "trade_fee": "5.0",
        "settlement_date": "2025-07-23T00:00:00",
        "created_at": datetime.now()
    }
    transaction = Transaction(**valid_payload)
    assert transaction.transaction_id == "test_txn_001"
    assert transaction.quantity == Decimal("10.0")

def test_transaction_model_missing_field_fails():
    """
    Tests that the Transaction model fails validation if a required field is missing.
    """
    invalid_payload = {
        "transaction_id": "test_txn_002",
        "portfolio_id": "test_port_002",
        "security_id": "SEC_GOOG",
        "transaction_date": "2025-07-22T00:00:00",
        "transaction_type": "SELL",
        "quantity": "5.0",
        "price": "200.0",
        "gross_transaction_amount": "1000.0",
        "trade_currency": "USD",
        "currency": "USD"
    }
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**invalid_payload)
    assert any("instrument_id" in err.get('loc', ()) for err in exc_info.value.errors())

def test_transaction_model_invalid_gross_amount_fails():
    """
    Tests that the Transaction model fails validation for invalid gross_transaction_amount (zero or negative).
    """
    base_payload = {
        "transaction_id": "txn_invalid_gross_amount", "portfolio_id": "P1", "instrument_id": "I1",
        "security_id": "S1", "transaction_date": "2025-01-01T00:00:00", "transaction_type": "BUY",
        "quantity": "10.0", "price": "100.0", "trade_currency": "USD", "currency": "USD"
    }
    payload_zero_gross = {**base_payload, "gross_transaction_amount": "0"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_zero_gross)
    assert any("greater than 0" in err['msg'] and "gross_transaction_amount" in str(err.get('loc')) for err in exc_info.value.errors())

def test_transaction_model_invalid_trade_fee_fails():
    """
    Tests that the Transaction model fails validation for invalid trade_fee (negative).
    """
    base_payload = {
        "transaction_id": "txn_invalid_fee", "portfolio_id": "P1", "instrument_id": "I1",
        "security_id": "S1", "transaction_date": "2025-01-01T00:00:00", "transaction_type": "BUY",
        "quantity": "10.0", "price": "100.0", "gross_transaction_amount": "1000.0",
        "trade_currency": "USD", "currency": "USD"
    }
    payload_neg_fee = {**base_payload, "trade_fee": "-5.0"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_neg_fee)
    assert any("greater than or equal to 0" in err['msg'] and "trade_fee" in str(err.get('loc')) for err in exc_info.value.errors())

def test_transaction_model_non_numeric_input_fails():
    """
    Tests that the Transaction model fails validation for non-numeric input for Decimal fields.
    """
    base_payload = {
        "transaction_id": "txn_non_numeric", "portfolio_id": "P1", "instrument_id": "I1",
        "security_id": "S1", "transaction_date": "2025-01-01T00:00:00", "transaction_type": "BUY",
        "quantity": "10.0", "price": "100.0", "gross_transaction_amount": "1000.0",
        "trade_currency": "USD", "currency": "USD"
    }
    payload_non_numeric_qty = {**base_payload, "quantity": "abc"}
    with pytest.raises(ValidationError) as exc_info:
        Transaction(**payload_non_numeric_qty)
    assert any("valid decimal" in err['msg'] and "quantity" in str(err.get('loc')) for err in exc_info.value.errors())

def test_transaction_model_dividend_with_zero_qty_price_succeeds():
    """
    Tests that a DIVIDEND transaction with zero quantity and price is considered valid.
    """
    dividend_payload = {
        "transaction_id": "test_div_001",
        "portfolio_id": "test_port_001",
        "instrument_id": "IBM",
        "security_id": "SEC_IBM",
        "transaction_date": "2025-08-23T00:00:00",
        "transaction_type": "DIVIDEND",
        "quantity": "0",
        "price": "0",
        "gross_transaction_amount": "750.0",
        "trade_currency": "USD",
        "currency": "USD"
    }
    transaction = Transaction(**dividend_payload)
    assert transaction.quantity == Decimal("0")
    assert transaction.price == Decimal("0")