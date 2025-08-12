# tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py
import pytest
from decimal import Decimal
from datetime import datetime

from portfolio_common.events import TransactionEvent
from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import CashflowLogic
from src.services.calculators.cashflow_calculator_service.app.core.cashflow_config import get_rule_for_transaction

@pytest.fixture
def base_transaction_event() -> TransactionEvent:
    """Provides a base transaction event that can be customized in tests."""
    return TransactionEvent(
        transaction_id="TXN_CASHFLOW_01",
        portfolio_id="PORT_CF_01",
        instrument_id="INST_CF_01",
        security_id="SEC_CF_01",
        transaction_date=datetime(2025, 8, 1, 10, 0, 0),
        transaction_type="BUY", # Default type
        quantity=Decimal("100"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("1000"),
        trade_fee=Decimal("5.50"),
        trade_currency="USD",
        currency="USD",
    )

def test_calculate_buy_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a BUY transaction correctly generates a negative cashflow (outflow).
    """
    # Arrange
    event = base_transaction_event
    rule = get_rule_for_transaction("BUY")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    # Expected amount = -(Gross Amount + Fee)
    expected_amount = -(event.gross_transaction_amount + event.trade_fee)
    assert cashflow.amount == expected_amount
    assert cashflow.classification == "INVESTMENT_OUTFLOW"
    assert cashflow.timing == "EOD"
    assert cashflow.level == "POSITION"

def test_calculate_sell_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a SELL transaction correctly generates a positive cashflow (inflow).
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "SELL"
    rule = get_rule_for_transaction("SELL")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    # Expected amount = (Gross Amount - Fee)
    expected_amount = event.gross_transaction_amount - event.trade_fee
    assert cashflow.amount == expected_amount
    assert cashflow.classification == "INVESTMENT_INFLOW"
    assert cashflow.timing == "EOD"

def test_calculate_dividend_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a DIVIDEND transaction correctly generates a positive cashflow
    classified as INCOME with a BOD timing.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "DIVIDEND"
    event.gross_transaction_amount = Decimal("50") # Dividends are not based on quantity/price
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("DIVIDEND")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == event.gross_transaction_amount
    assert cashflow.classification == "INCOME"
    assert cashflow.timing == "BOD" # Dividends are typically BOD cashflows
    assert cashflow.level == "POSITION"

def test_calculate_fee_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a FEE transaction correctly generates a negative cashflow (outflow)
    at the PORTFOLIO level.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "FEE"
    event.gross_transaction_amount = Decimal("50")
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("FEE")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "EXPENSE"
    assert cashflow.level == "PORTFOLIO"
    assert cashflow.security_id is None

def test_calculate_interest_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that an INTEREST transaction correctly generates a positive cashflow
    classified as INCOME at the PORTFOLIO level.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "INTEREST"
    event.gross_transaction_amount = Decimal("75.25")
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("INTEREST")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == event.gross_transaction_amount
    assert cashflow.classification == "INCOME"
    assert cashflow.level == "PORTFOLIO"
    assert cashflow.security_id is None

def test_calculate_transfer_in_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a TRANSFER_IN transaction generates a positive BOD cashflow.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "TRANSFER_IN"
    event.gross_transaction_amount = Decimal("10000")
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("TRANSFER_IN")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == event.gross_transaction_amount
    assert cashflow.classification == "CASHFLOW_IN"
    assert cashflow.timing == "BOD"
    assert cashflow.level == "PORTFOLIO"

def test_calculate_transfer_out_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a TRANSFER_OUT transaction generates a negative EOD cashflow.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "TRANSFER_OUT"
    event.gross_transaction_amount = Decimal("2500")
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("TRANSFER_OUT")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "CASHFLOW_OUT"
    assert cashflow.timing == "EOD"
    assert cashflow.level == "PORTFOLIO"

def test_calculate_tax_transaction(base_transaction_event: TransactionEvent):
    """
    Tests that a TAX transaction generates a negative expense cashflow.
    """
    # Arrange
    event = base_transaction_event
    event.transaction_type = "TAX"
    event.gross_transaction_amount = Decimal("123.45")
    event.trade_fee = Decimal("0")
    rule = get_rule_for_transaction("TAX")
    assert rule is not None

    # Act
    cashflow = CashflowLogic.calculate(event, rule)

    # Assert
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "EXPENSE"
    assert cashflow.level == "PORTFOLIO"