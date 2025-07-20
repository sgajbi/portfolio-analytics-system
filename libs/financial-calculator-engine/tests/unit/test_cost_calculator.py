# tests/unit/test_cost_calculator.py

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.logic.cost_calculator import CostCalculator
from src.logic.disposition_engine import DispositionEngine
from src.logic.error_reporter import ErrorReporter
from src.core.models.transaction import Transaction, Fees
from src.core.enums.transaction_type import TransactionType

@pytest.fixture
def mock_disposition_engine():
    return MagicMock(spec=DispositionEngine)

@pytest.fixture
def error_reporter():
    return ErrorReporter()

@pytest.fixture
def cost_calculator(mock_disposition_engine, error_reporter):
    return CostCalculator(disposition_engine=mock_disposition_engine, error_reporter=error_reporter)

@pytest.fixture
def buy_transaction():
    return Transaction(
        transaction_id="BUY001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type=TransactionType.BUY, transaction_date=date(2023, 1, 1), settlement_date=date(2023, 1, 3),
        quantity=Decimal("10"), gross_transaction_amount=Decimal("1500"), trade_currency="USD",
        fees=Fees(brokerage=Decimal("5.5")), accrued_interest=Decimal("10.0")
    )

@pytest.fixture
def sell_transaction():
    return Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type=TransactionType.SELL, transaction_date=date(2023, 1, 10), settlement_date=date(2023, 1, 12),
        quantity=Decimal("5"), gross_transaction_amount=Decimal("800"), trade_currency="USD",
        fees=Fees(brokerage=Decimal("3.0"))
    )

def test_buy_strategy(cost_calculator, mock_disposition_engine, buy_transaction):
    cost_calculator.calculate_transaction_costs(buy_transaction)
    assert buy_transaction.net_cost == Decimal("1515.5")
    assert buy_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)

def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    mock_disposition_engine.consume_sell_quantity.return_value = (Decimal("500"), Decimal("5"), None)
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0") # 800 - 500 - 3.0
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)