# tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py
import pytest
from decimal import Decimal
from datetime import datetime

from portfolio_common.events import TransactionEvent
from portfolio_common.database_models import CashflowRule
from src.services.calculators.cashflow_calculator_service.app.core.cashflow_logic import CashflowLogic
from src.services.calculators.cashflow_calculator_service.app.core.enums import CashflowClassification, CashflowTiming

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
    """A BUY is a negative cashflow (outflow)."""
    event = base_transaction_event
    rule = CashflowRule(classification=CashflowClassification.INVESTMENT_OUTFLOW, timing=CashflowTiming.BOD, is_position_flow=True, is_portfolio_flow=False)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount < 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False

def test_calculate_sell_transaction(base_transaction_event: TransactionEvent):
    """A SELL is a positive cashflow (inflow)."""
    event = base_transaction_event
    event.transaction_type = "SELL"
    rule = CashflowRule(classification=CashflowClassification.INVESTMENT_INFLOW, timing=CashflowTiming.EOD, is_position_flow=True, is_portfolio_flow=False)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount > 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False

def test_calculate_dividend_transaction(base_transaction_event: TransactionEvent):
    """A DIVIDEND is a positive cashflow (inflow)."""
    event = base_transaction_event
    event.transaction_type = "DIVIDEND"
    rule = CashflowRule(classification=CashflowClassification.INCOME, timing=CashflowTiming.EOD, is_position_flow=True, is_portfolio_flow=False)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount > 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is False
    assert cashflow.timing == "EOD"

def test_calculate_deposit_transaction(base_transaction_event: TransactionEvent):
    """A DEPOSIT is a positive cashflow (inflow)."""
    event = base_transaction_event
    event.transaction_type = "DEPOSIT"
    rule = CashflowRule(classification=CashflowClassification.CASHFLOW_IN, timing=CashflowTiming.BOD, is_position_flow=True, is_portfolio_flow=True)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.classification == "CASHFLOW_IN"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0

def test_calculate_fee_transaction(base_transaction_event: TransactionEvent):
    """A FEE is a negative cashflow (outflow)."""
    event = base_transaction_event
    event.transaction_type = "FEE"
    rule = CashflowRule(classification=CashflowClassification.EXPENSE, timing=CashflowTiming.EOD, is_position_flow=True, is_portfolio_flow=True)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount < 0
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True

def test_calculate_withdrawal_transaction(base_transaction_event: TransactionEvent):
    """A WITHDRAWAL is a negative cashflow (outflow)."""
    event = base_transaction_event
    event.transaction_type = "WITHDRAWAL"
    event.gross_transaction_amount = Decimal("5000")
    event.trade_fee = Decimal("0")
    rule = CashflowRule(classification=CashflowClassification.CASHFLOW_OUT, timing=CashflowTiming.EOD, is_position_flow=True, is_portfolio_flow=True)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.amount == -event.gross_transaction_amount
    assert cashflow.classification == "CASHFLOW_OUT"
    assert cashflow.timing == "EOD"
    assert cashflow.is_position_flow is True
    assert cashflow.is_portfolio_flow is True

def test_calculate_transfer_in_transaction(base_transaction_event: TransactionEvent):
    """A TRANSFER_IN is a positive cashflow (inflow)."""
    event = base_transaction_event
    event.transaction_type = "TRANSFER_IN"
    rule = CashflowRule(classification=CashflowClassification.TRANSFER, timing=CashflowTiming.BOD, is_position_flow=True, is_portfolio_flow=True)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount > 0

def test_calculate_transfer_out_transaction(base_transaction_event: TransactionEvent):
    """A TRANSFER_OUT is a negative cashflow (outflow)."""
    event = base_transaction_event
    event.transaction_type = "TRANSFER_OUT"
    rule = CashflowRule(classification=CashflowClassification.TRANSFER, timing=CashflowTiming.EOD, is_position_flow=True, is_portfolio_flow=True)
    assert rule is not None
    cashflow = CashflowLogic.calculate(event, rule)
    assert cashflow.classification == "TRANSFER"
    assert cashflow.is_portfolio_flow is True
    assert cashflow.amount < 0