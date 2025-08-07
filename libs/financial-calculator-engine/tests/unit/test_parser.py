# tests/unit/test_parser.py

import pytest
from datetime import date
from decimal import Decimal

from logic.parser import TransactionParser
from logic.error_reporter import ErrorReporter

@pytest.fixture
def error_reporter():
    return ErrorReporter()

@pytest.fixture
def parser(error_reporter):
    return TransactionParser(error_reporter=error_reporter)

def test_parse_valid_transaction(parser, error_reporter):
    raw_data = [{
        "transaction_id": "txn1", "portfolio_id": "P1", "instrument_id": "AAPL", "security_id": "S1",
        "transaction_type": "BUY", "transaction_date": "2023-01-01T00:00:00Z", "settlement_date": "2023-01-03T00:00:00Z",
        "quantity": 10.0, "gross_transaction_amount": 1500.0, "trade_currency": "USD"
    }]
    parsed = parser.parse_transactions(raw_data)
    assert len(parsed) == 1
    assert not error_reporter.has_errors()
    assert parsed[0].quantity == Decimal("10.0")

def test_parse_invalid_transaction(parser, error_reporter):
    raw_data = [{"transaction_id": "txn1"}] # Missing fields
    parsed = parser.parse_transactions(raw_data)
    assert len(parsed) == 1
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn1")