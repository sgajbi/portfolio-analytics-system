# services/calculators/cashflow_calculator_service/tests/unit/core/test_cashflow_logic.py
import pytest
from decimal import Decimal
from datetime import datetime

from portfolio_common.events import TransactionEvent
from services.calculators.cashflow_calculator_service.app.core.cashflow_logic import CashflowLogic
from services.calculators.cashflow_calculator_service.app.core.cashflow_config import get_rule_for_transaction

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