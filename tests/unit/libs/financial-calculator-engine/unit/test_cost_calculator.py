# libs/financial-calculator-engine/tests/unit/test_cost_calculator.py

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from logic.cost_basis_strategies import FIFOBasisStrategy
from logic.disposition_engine import DispositionEngine

from logic.cost_calculator import CostCalculator
from logic.error_reporter import ErrorReporter
from core.models.transaction import Transaction, Fees
from core.enums.transaction_type import TransactionType

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
        transaction_type=TransactionType.BUY, transaction_date=datetime(2023, 1, 1), settlement_date=datetime(2023, 1, 3),
        quantity=Decimal("10"), gross_transaction_amount=Decimal("1500"), trade_currency="USD",
        fees=Fees(brokerage=Decimal("5.5")), accrued_interest=Decimal("10.0"),
        # --- FIX: Add required field ---
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )

@pytest.fixture
def sell_transaction():
    return Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type=TransactionType.SELL, transaction_date=datetime(2023, 1, 10), settlement_date=datetime(2023, 1, 12),
        quantity=Decimal("5"), gross_transaction_amount=Decimal("800"), trade_currency="USD",
        fees=Fees(brokerage=Decimal("3.0")),
        # --- FIX: Add required field ---
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )

def test_buy_strategy(cost_calculator, mock_disposition_engine, buy_transaction):
    cost_calculator.calculate_transaction_costs(buy_transaction)
    assert buy_transaction.net_cost == Decimal("1515.5")
    assert buy_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)

def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    # cogs_base, cogs_local, consumed_quantity, error_reason
    mock_disposition_engine.consume_sell_quantity.return_value = (Decimal("500"), Decimal("500"), Decimal("5"), None)
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0") # 800 - 3.0 - 500
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)

# --- NEW: A more comprehensive integration test for the calculator logic ---

def test_sell_strategy_multi_lot_fifo():
    """
    Tests the FIFO strategy across multiple purchase lots.
    Scenario:
    1. Buy 100 shares @ $10/share (net_cost=$1000)
    2. Buy 50 shares @ $12/share (net_cost=$600)
    3. Sell 120 shares @ $15/share (proceeds=$1800)
    """
    # Arrange: Use real components for a more valuable test of the core logic.
    error_reporter = ErrorReporter()
    fifo_strategy = FIFOBasisStrategy()
    disposition_engine = DispositionEngine(cost_basis_strategy=fifo_strategy)
    cost_calculator = CostCalculator(
        disposition_engine=disposition_engine, error_reporter=error_reporter
    )

    # Act: Process the transactions in chronological order.
    buy_txn_1 = Transaction(
        transaction_id="BUY001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("1000"), trade_currency="USD",
        # --- FIX: Add required fields ---
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_1) # This calculates net_cost=1000 and adds the lot.

    buy_txn_2 = Transaction(
        transaction_id="BUY002", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"), gross_transaction_amount=Decimal("600"), trade_currency="USD",
        # --- FIX: Add required fields ---
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_2) # This calculates net_cost=600 and adds the second lot.

    sell_txn = Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="SELL", transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("120"), gross_transaction_amount=Decimal("1800"), trade_currency="USD",
        # --- FIX: Add required fields ---
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(sell_txn) # This calculates the gain/loss.
    # Assert: Verify the calculated realized gain and the state of the remaining lots.
    # Cost of goods sold = (100 shares * $10) + (20 shares * $12) = 1000 + 240 = 1240
    # Realized Gain/Loss = Net Proceeds - COGS = 1800 - 1240 = 560
    assert sell_txn.realized_gain_loss == Decimal("560")
    assert not error_reporter.has_errors()

    # Assert that 30 shares from the second lot remain.
    remaining_quantity = disposition_engine.get_available_quantity("P1", "AAPL")
    assert remaining_quantity == Decimal("30")