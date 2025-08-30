# tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py

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
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )

@pytest.fixture
def sell_transaction():
    return Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type=TransactionType.SELL, transaction_date=datetime(2023, 1, 10), settlement_date=datetime(2023, 1, 12),
        quantity=Decimal("5"), gross_transaction_amount=Decimal("800"), trade_currency="USD",
        fees=Fees(brokerage=Decimal("3.0")),
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )

def test_buy_strategy(cost_calculator, mock_disposition_engine, buy_transaction):
    cost_calculator.calculate_transaction_costs(buy_transaction)
    assert buy_transaction.net_cost_local == Decimal("1515.5") # Cost in trade currency
    assert buy_transaction.net_cost == Decimal("1515.5") # Cost in base currency (FX rate is 1.0)
    assert buy_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)

def test_buy_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    """
    Tests that a BUY transaction's cost is correctly calculated in both local (trade)
    and base (portfolio) currencies when they differ.
    """
    # Arrange: A USD portfolio buying a EUR-denominated asset
    dual_currency_buy = Transaction(
        transaction_id="DC_BUY_01", portfolio_id="P_USD", instrument_id="AIR.PA", security_id="S_AIR",
        transaction_type=TransactionType.BUY, transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("15000"), trade_currency="EUR",
        fees=Fees(brokerage=Decimal("10")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.15")  # 1 EUR = 1.15 USD
    )

    # Act
    cost_calculator.calculate_transaction_costs(dual_currency_buy)

    # Assert
    # Net cost in local (trade) currency: 15000 EUR + 10 EUR fee
    assert dual_currency_buy.net_cost_local == Decimal("15010")
    # Net cost in base (portfolio) currency: 15010 EUR * 1.15 USD/EUR
    assert dual_currency_buy.net_cost == Decimal("17261.50")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(dual_currency_buy)


def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    # cogs_base, cogs_local, consumed_quantity, error_reason
    mock_disposition_engine.consume_sell_quantity.return_value = (Decimal("500"), Decimal("500"), Decimal("5"), None)
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0") # 800 - 3.0 - 500
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)

def test_sell_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    """
    Tests that a SELL transaction's P&L is correctly calculated in both local (trade)
    and base (portfolio) currencies when they differ.
    """
    # Arrange: A USD portfolio selling a EUR-denominated asset
    dual_currency_sell = Transaction(
        transaction_id="DC_SELL_01", portfolio_id="P_USD", instrument_id="AIR.PA", security_id="S_AIR",
        transaction_type=TransactionType.SELL, transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("50"), gross_transaction_amount=Decimal("8000"), trade_currency="EUR",
        fees=Fees(brokerage=Decimal("8")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.20")  # 1 EUR = 1.20 USD
    )
    # Mock the disposition engine returning the cost of goods sold in both currencies
    # e.g., the 50 shares cost €7,500, which was $8,250 at the time of purchase
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("8250"), # cogs_base (USD)
        Decimal("7500"), # cogs_local (EUR)
        Decimal("50"),   # consumed_quantity
        None             # error_reason
    )

    # Act
    cost_calculator.calculate_transaction_costs(dual_currency_sell)

    # Assert
    # Net Proceeds (Local) = 8000 EUR - 8 EUR fee = 7992 EUR
    # Realized P&L (Local) = 7992 EUR (Proceeds) - 7500 EUR (COGS) = 492 EUR
    assert dual_currency_sell.realized_gain_loss_local == Decimal("492")

    # Net Proceeds (Base) = 7992 EUR * 1.20 USD/EUR = 9590.40 USD
    # Realized P&L (Base) = 9590.40 USD (Proceeds) - 8250 USD (COGS) = 1340.40 USD
    assert dual_currency_sell.realized_gain_loss.quantize(Decimal("0.01")) == Decimal("1340.40")
    
    # Verify net_cost is also populated correctly
    assert dual_currency_sell.net_cost == Decimal("-8250")
    assert dual_currency_sell.net_cost_local == Decimal("-7500")

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
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_1)

    buy_txn_2 = Transaction(
        transaction_id="BUY002", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("50"), gross_transaction_amount=Decimal("600"), trade_currency="USD",
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_2)

    sell_txn = Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="SELL", transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("120"), gross_transaction_amount=Decimal("1800"), trade_currency="USD",
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(sell_txn)

    # Assert: Verify the calculated realized gain and the state of the remaining lots.
    assert sell_txn.realized_gain_loss == Decimal("560")
    assert not error_reporter.has_errors()

    remaining_quantity = disposition_engine.get_available_quantity("P1", "AAPL")
    assert remaining_quantity == Decimal("30")

def test_deposit_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    """
    Tests that a DEPOSIT transaction correctly uses the CashInflowStrategy
    to create a cost lot in the disposition engine.
    """
    # Arrange
    deposit_transaction = Transaction(
        transaction_id="DEPOSIT001", portfolio_id="P1", instrument_id="CASH_USD", security_id="CASH_USD",
        transaction_type=TransactionType.DEPOSIT, transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"), price=Decimal("1"), gross_transaction_amount=Decimal("10000"),
        trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )

    # Act
    cost_calculator.calculate_transaction_costs(deposit_transaction)

    # Assert
    assert deposit_transaction.net_cost == Decimal("10000")
    assert deposit_transaction.gross_cost == Decimal("10000")
    
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    
    assert call_args.quantity == Decimal("10000")

def test_dividend_transaction_has_zero_cost(cost_calculator, mock_disposition_engine):
    """
    Tests that a DIVIDEND transaction is processed but results in a net_cost of zero,
    as it represents income and does not alter the position's cost basis.
    """
    # ARRANGE
    dividend_transaction = Transaction(
        transaction_id="DIV001",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type=TransactionType.DIVIDEND,
        transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("500.00"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0")
    )

    # ACT
    cost_calculator.calculate_transaction_costs(dividend_transaction)

    # ASSERT
    assert dividend_transaction.net_cost == Decimal("0")
    assert dividend_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_not_called()

# --- NEW FAILING TEST (TDD) ---
def test_transfer_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    """
    Tests that a TRANSFER_IN transaction creates a cost lot in the disposition engine,
    similar to a BUY or DEPOSIT. This will fail with the DefaultStrategy.
    """
    # Arrange
    transfer_in_transaction = Transaction(
        transaction_id="TRANSFER_IN_01",
        portfolio_id="P1",
        instrument_id="IBM",
        security_id="S_IBM",
        transaction_type="TRANSFER_IN", # Custom transaction type
        transaction_date=datetime(2023, 2, 1),
        quantity=Decimal("100"),
        price=Decimal("150"),
        gross_transaction_amount=Decimal("15000"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0")
    )

    # Act
    cost_calculator.calculate_transaction_costs(transfer_in_transaction)

    # Assert
    # The transaction should have its cost calculated
    assert transfer_in_transaction.net_cost == Decimal("15000")

    # The disposition engine should have been told to create a lot for these shares
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("100")
    assert call_args.net_cost == Decimal("15000")