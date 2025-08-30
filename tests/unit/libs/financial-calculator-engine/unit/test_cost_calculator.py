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
    assert buy_transaction.net_cost_local == Decimal("1515.5")
    assert buy_transaction.net_cost == Decimal("1515.5")
    assert buy_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_called_once_with(buy_transaction)

def test_buy_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_buy = Transaction(
        transaction_id="DC_BUY_01", portfolio_id="P_USD", instrument_id="AIR.PA", security_id="S_AIR",
        transaction_type=TransactionType.BUY, transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("15000"), trade_currency="EUR",
        fees=Fees(brokerage=Decimal("10")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.15")
    )
    cost_calculator.calculate_transaction_costs(dual_currency_buy)
    assert dual_currency_buy.net_cost_local == Decimal("15010")
    assert dual_currency_buy.net_cost == Decimal("17261.50")
    mock_disposition_engine.add_buy_lot.assert_called_once_with(dual_currency_buy)


def test_sell_strategy_gain(cost_calculator, mock_disposition_engine, sell_transaction):
    mock_disposition_engine.consume_sell_quantity.return_value = (Decimal("500"), Decimal("500"), Decimal("5"), None)
    cost_calculator.calculate_transaction_costs(sell_transaction)
    assert sell_transaction.realized_gain_loss == Decimal("297.0")
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(sell_transaction)

def test_sell_strategy_dual_currency(cost_calculator, mock_disposition_engine):
    dual_currency_sell = Transaction(
        transaction_id="DC_SELL_01", portfolio_id="P_USD", instrument_id="AIR.PA", security_id="S_AIR",
        transaction_type=TransactionType.SELL, transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("50"), gross_transaction_amount=Decimal("8000"), trade_currency="EUR",
        fees=Fees(brokerage=Decimal("8")),
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.20")
    )
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("8250"), Decimal("7500"), Decimal("50"), None
    )
    cost_calculator.calculate_transaction_costs(dual_currency_sell)
    assert dual_currency_sell.realized_gain_loss_local == Decimal("492")
    assert dual_currency_sell.realized_gain_loss.quantize(Decimal("0.01")) == Decimal("1340.40")
    assert dual_currency_sell.net_cost == Decimal("-8250")
    assert dual_currency_sell.net_cost_local == Decimal("-7500")

def test_sell_strategy_multi_lot_fifo():
    error_reporter = ErrorReporter()
    fifo_strategy = FIFOBasisStrategy()
    disposition_engine = DispositionEngine(cost_basis_strategy=fifo_strategy)
    cost_calculator = CostCalculator(
        disposition_engine=disposition_engine, error_reporter=error_reporter
    )
    buy_txn_1 = Transaction(
        transaction_id="BUY001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 1), quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"), net_cost=Decimal("1000"), net_cost_local=Decimal("1000"), trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_1)
    buy_txn_2 = Transaction(
        transaction_id="BUY002", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 5), quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"), net_cost=Decimal("600"), net_cost_local=Decimal("600"), trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(buy_txn_2)
    sell_txn = Transaction(
        transaction_id="SELL001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type="SELL", transaction_date=datetime(2023, 1, 10),
        quantity=Decimal("120"), gross_transaction_amount=Decimal("1800"), trade_currency="USD",
        portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(sell_txn)
    assert sell_txn.realized_gain_loss == Decimal("560")
    assert not error_reporter.has_errors()
    assert disposition_engine.get_available_quantity("P1", "AAPL") == Decimal("30")

def test_deposit_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    deposit_transaction = Transaction(
        transaction_id="DEPOSIT001", portfolio_id="P1", instrument_id="CASH_USD", security_id="CASH_USD",
        transaction_type=TransactionType.DEPOSIT, transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("10000"), price=Decimal("1"), gross_transaction_amount=Decimal("10000"),
        trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(deposit_transaction)
    assert deposit_transaction.net_cost == Decimal("10000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("10000")

def test_dividend_transaction_has_zero_cost(cost_calculator, mock_disposition_engine):
    dividend_transaction = Transaction(
        transaction_id="DIV001", portfolio_id="P1", instrument_id="AAPL", security_id="S1",
        transaction_type=TransactionType.DIVIDEND, transaction_date=datetime(2023, 1, 15),
        quantity=Decimal("0"), price=Decimal("0"), gross_transaction_amount=Decimal("500.00"),
        trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(dividend_transaction)
    assert dividend_transaction.net_cost == Decimal("0")
    assert dividend_transaction.realized_gain_loss is None
    mock_disposition_engine.add_buy_lot.assert_not_called()

def test_transfer_in_strategy_creates_cost_lot(cost_calculator, mock_disposition_engine):
    transfer_in_transaction = Transaction(
        transaction_id="TRANSFER_IN_01", portfolio_id="P1", instrument_id="IBM", security_id="S_IBM",
        transaction_type="TRANSFER_IN", transaction_date=datetime(2023, 2, 1),
        quantity=Decimal("100"), price=Decimal("150"), gross_transaction_amount=Decimal("15000"),
        trade_currency="USD", portfolio_base_currency="USD", transaction_fx_rate=Decimal("1.0")
    )
    cost_calculator.calculate_transaction_costs(transfer_in_transaction)
    assert transfer_in_transaction.net_cost == Decimal("15000")
    mock_disposition_engine.add_buy_lot.assert_called_once()
    call_args = mock_disposition_engine.add_buy_lot.call_args[0][0]
    assert call_args.quantity == Decimal("100")
    assert call_args.net_cost == Decimal("15000")

# --- NEW FAILING TEST (TDD) ---
def test_transfer_out_strategy_consumes_lot_without_pnl(cost_calculator, mock_disposition_engine):
    """
    Tests that a TRANSFER_OUT transaction consumes a cost lot but does not generate P&L.
    This will fail with the DefaultStrategy.
    """
    # Arrange
    transfer_out_transaction = Transaction(
        transaction_id="TRANSFER_OUT_01",
        portfolio_id="P1",
        instrument_id="AAPL",
        security_id="S1",
        transaction_type="TRANSFER_OUT",
        transaction_date=datetime(2023, 2, 15),
        quantity=Decimal("20"),
        price=Decimal("160"),
        gross_transaction_amount=Decimal("3200"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1.0")
    )
    
    # Simulate the disposition engine returning the cost of the transferred shares
    mock_disposition_engine.consume_sell_quantity.return_value = (
        Decimal("3000"), Decimal("3000"), Decimal("20"), None
    )

    # Act
    cost_calculator.calculate_transaction_costs(transfer_out_transaction)

    # Assert
    # It should have called the disposition engine to "consume" the shares
    mock_disposition_engine.consume_sell_quantity.assert_called_once_with(transfer_out_transaction)

    # Crucially, it should NOT have calculated a realized gain/loss
    assert transfer_out_transaction.realized_gain_loss is None