import pytest
from decimal import Decimal
from datetime import datetime

from services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from services.calculators.position_calculator.app.core.position_models import PositionState
from portfolio_common.events import TransactionEvent

@pytest.fixture
def zero_position_state() -> PositionState:
    """Returns a position state with zero quantity and cost basis."""
    return PositionState(quantity=Decimal(0), cost_basis=Decimal(0))

@pytest.fixture
def existing_position_state() -> PositionState:
    """Returns a position state representing an existing holding."""
    # Represents 100 shares bought for a total of $10,000
    return PositionState(quantity=Decimal("100"), cost_basis=Decimal("10000"))

def test_calculate_next_position_buy_from_zero(zero_position_state):
    """
    Tests a BUY transaction starting from no position.
    """
    buy_transaction = TransactionEvent(
        transaction_id="T1",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        transaction_type="BUY",
        quantity=Decimal("50"),
        price=Decimal("110"),
        gross_transaction_amount=Decimal("5500"),
        trade_currency="USD",
        currency="USD",
        net_cost=Decimal("5505")  # Includes $5 fee
    )

    new_state = PositionCalculator.calculate_next_position(zero_position_state, buy_transaction)

    assert new_state.quantity == Decimal("50")
    assert new_state.cost_basis == Decimal("5505")

def test_calculate_next_position_sell_partial(existing_position_state):
    """
    Tests a partial SELL from an existing position.
    The average cost per share is $10000 / 100 = $100.
    """
    sell_transaction = TransactionEvent(
        transaction_id="T2",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        transaction_type="SELL",
        quantity=Decimal("40"),
        price=Decimal("120"),
        gross_transaction_amount=Decimal("4800"),
        trade_currency="USD",
        currency="USD"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, sell_transaction)

    # Quantity should decrease by 40 (100 -> 60)
    assert new_state.quantity == Decimal("60")
    # Cost basis should decrease by the cost of goods sold (40 shares * $100/share = $4000)
    # 10000 - 4000 = 6000
    assert new_state.cost_basis == Decimal("6000")

def test_calculate_next_position_sell_full(existing_position_state):
    """
    Tests a SELL that fully closes the position.
    """
    sell_transaction = TransactionEvent(
        transaction_id="T3",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        transaction_type="SELL",
        quantity=Decimal("100"),
        price=Decimal("120"),
        gross_transaction_amount=Decimal("12000"),
        trade_currency="USD",
        currency="USD"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, sell_transaction)

    assert new_state.quantity == Decimal("0")
    assert new_state.cost_basis == Decimal("0")

def test_other_transaction_types_do_not_change_state(existing_position_state):
    """
    Tests that non-BUY/SELL transactions do not alter the quantity or cost basis.
    """
    fee_transaction = TransactionEvent(
        transaction_id="T4",
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime.now(),
        transaction_type="FEE",
        quantity=Decimal("1"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="USD",
        currency="USD"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, fee_transaction)

    # State should be unchanged
    assert new_state.quantity == existing_position_state.quantity
    assert new_state.cost_basis == existing_position_state.cost_basis