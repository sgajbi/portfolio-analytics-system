# libs/financial-calculator-engine/tests/unit/test_cost_basis_strategies.py
import pytest
from datetime import date
from decimal import Decimal

from src.core.models.transaction import Transaction
from src.logic.cost_basis_strategies import AverageCostBasisStrategy

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
        transaction_type="BUY", transaction_date=date(2023, 1, 1),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("1000"), net_cost=Decimal("1000"),
        trade_currency="USD"
    )
    buy_txn_2 = Transaction(
        transaction_id="BUY002", portfolio_id="P1", instrument_id="AVCO_STOCK", security_id="S1",
        transaction_type="BUY", transaction_date=date(2023, 1, 5),
        quantity=Decimal("100"), gross_transaction_amount=Decimal("1200"), net_cost=Decimal("1200"),
        trade_currency="USD"
    )

    # Act: Add the buy lots to the strategy
    avco_strategy.add_buy_lot(buy_txn_1)
    avco_strategy.add_buy_lot(buy_txn_2)

    # Assert initial state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("200")

    # Act: Consume a partial sell
    sell_quantity = Decimal("50")
    total_matched_cost, consumed_quantity, error = avco_strategy.consume_sell_quantity(
        portfolio_id="P1", instrument_id="AVCO_STOCK", required_quantity=sell_quantity
    )

    # Assert the results of the disposition
    # Expected cost of goods sold = 50 shares * $11 avg_cost = $550
    assert total_matched_cost == Decimal("550")
    assert consumed_quantity == sell_quantity
    assert error is None

    # Assert the final state
    assert avco_strategy.get_available_quantity("P1", "AVCO_STOCK") == Decimal("150")