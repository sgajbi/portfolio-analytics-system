# tests/unit/libs/financial-calculator-engine/unit/test_cost_basis_strategies.py
import pytest
from datetime import datetime
from decimal import Decimal

from core.models.transaction import Transaction
from logic.cost_basis_strategies import AverageCostBasisStrategy, FIFOBasisStrategy
from logic.cost_objects import CostLot

# --- Tests for AverageCostBasisStrategy ---

@pytest.fixture
def avco_strategy():
    """Provides a clean instance of the AverageCostBasisStrategy."""
    return AverageCostBasisStrategy()


def test_average_cost_simple_disposition(avco_strategy: AverageCostBasisStrategy):
    """
    Tests a standard scenario for the Average Cost method.
    Scenario:
    1. Buy 100 shares for a total net cost of $1000.
    2. Buy 100 shares for a total net cost of $1200.
    - Total position: 200 shares, total cost: $2200, average cost: $11/share.
    3. Sell 50 shares.
    """
    # Arrange: Create the two buy transactions
    buy_txn_1 = Transaction(
        transaction_id="BUY001", portfolio_id="P1", instrument_id="AVCO_STOCK", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("1000"), net_cost=Decimal("1000"),
        trade_currency="USD", portfolio_base_currency="USD", net_cost_local=Decimal("1000")
    )
    buy_txn_2 = Transaction(
        transaction_id="BUY002", portfolio_id="P1", instrument_id="AVCO_STOCK", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 5),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("1200"), net_cost=Decimal("1200"),
        trade_currency="USD", portfolio_base_currency="USD", net_cost_local=Decimal("1200")
    )

    # Act: Add the buy lots to the strategy
    avco_strategy.add_buy_lot(buy_txn_1)
    avco_strategy.add_buy_lot(buy_txn_2)

    # Assert initial state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("200")

    # Act: Consume a partial sell
    sell_quantity = Decimal("50")
    total_matched_cost_base, total_matched_cost_local, consumed_quantity, error = avco_strategy.consume_sell_quantity(
        portfolio_id="P1", instrument_id="AVCO_STOCK", required_quantity=sell_quantity
    )

    # Assert the results of the disposition
    # Expected cost of goods sold = 50 shares * $11 avg_cost = $550
    assert total_matched_cost_base == Decimal("550")
    assert consumed_quantity == sell_quantity
    assert error is None

    # Assert the final state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("150")

# --- Tests for FIFOBasisStrategy ---

@pytest.fixture
def fifo_strategy() -> FIFOBasisStrategy:
    """Provides a clean instance of the FIFOBasisStrategy."""
    return FIFOBasisStrategy()

@pytest.fixture
def sample_buy_transaction() -> Transaction:
    """Provides a sample BUY transaction for FIFO tests."""
    return Transaction(
        transaction_id="FIFO_BUY_01",
        portfolio_id="P1",
        instrument_id="FIFO_STOCK",
        security_id="S1",
        transaction_type="BUY",
        transaction_date=datetime(2023, 1, 1),
        quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1010"), # Includes $10 fee
        net_cost_local=Decimal("1010"),
        trade_currency="USD",
        portfolio_base_currency="USD"
    )

def test_fifo_add_buy_lot(fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: Transaction):
    # Act
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Assert
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("100")
    lot_key = ("P1", "FIFO_STOCK")
    assert len(fifo_strategy._open_lots[lot_key]) == 1
    lot = fifo_strategy._open_lots[lot_key][0]
    assert lot.cost_per_share_base == Decimal("10.10") # 1010 / 100

def test_fifo_consume_sell_fully(fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: Transaction):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("100")
    )

    # Assert
    assert cost_base == Decimal("1010")
    assert consumed_qty == Decimal("100")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("0")

def test_fifo_consume_sell_partially(fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: Transaction):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("40")
    )

    # Assert
    assert cost_base == Decimal("404") # 40 shares * $10.10/share
    assert consumed_qty == Decimal("40")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("60")
    lot_key = ("P1", "FIFO_STOCK")
    assert fifo_strategy._open_lots[lot_key][0].remaining_quantity == Decimal("60")

def test_fifo_consume_sell_insufficient_quantity(fifo_strategy: FIFOBasisStrategy, sample_buy_transaction: Transaction):
    # Arrange
    fifo_strategy.add_buy_lot(sample_buy_transaction)

    # Act
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("101")
    )

    # Assert
    assert cost_base == Decimal("0")
    assert consumed_qty == Decimal("0")
    # FIX: Corrected assertion to match the actual error message format
    assert error == "Sell quantity (101) exceeds available holdings (100)."
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("100")

def test_fifo_multi_lot_disposition(fifo_strategy: FIFOBasisStrategy):
    # Arrange: Two buy lots
    buy1 = Transaction(
        transaction_id="FIFO_BUY_01", portfolio_id="P1", instrument_id="FIFO_STOCK", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 1), quantity=Decimal("100"),
        gross_transaction_amount=Decimal("1000"),
        net_cost=Decimal("1000"), net_cost_local=Decimal("1000"), trade_currency="USD", portfolio_base_currency="USD"
    ) # Cost: $10/share
    buy2 = Transaction(
        transaction_id="FIFO_BUY_02", portfolio_id="P1", instrument_id="FIFO_STOCK", security_id="S1",
        transaction_type="BUY", transaction_date=datetime(2023, 1, 5), quantity=Decimal("50"),
        gross_transaction_amount=Decimal("600"),
        net_cost=Decimal("600"), net_cost_local=Decimal("600"), trade_currency="USD", portfolio_base_currency="USD"
    ) # Cost: $12/share

    fifo_strategy.add_buy_lot(buy1)
    fifo_strategy.add_buy_lot(buy2)
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("150")

    # Act: Sell 120 shares. This should consume all of buy1 and 20 shares of buy2.
    cost_base, cost_local, consumed_qty, error = fifo_strategy.consume_sell_quantity(
        "P1", "FIFO_STOCK", Decimal("120")
    )

    # Assert
    # COGS = (100 shares * $10) + (20 shares * $12) = 1000 + 240 = 1240
    assert cost_base == Decimal("1240")
    assert consumed_qty == Decimal("120")
    assert error is None
    assert fifo_strategy.get_available_quantity("P1", "FIFO_STOCK") == Decimal("30")
    lot_key = ("P1", "FIFO_STOCK")
    assert len(fifo_strategy._open_lots[lot_key]) == 1
    assert fifo_strategy._open_lots[lot_key][0].remaining_quantity == Decimal("30")


