import pytest
from decimal import Decimal
from datetime import datetime

from services.calculators.position_calculator.app.core.position_logic import PositionCalculator
from services.calculators.position_calculator.app.core.position_models import PositionState
from portfolio_common.events import TransactionEvent

@pytest.fixture
def zero_position_state() -> PositionState:
    """Returns a position state with zero quantity and cost basis."""
    return PositionState(quantity=Decimal(0), cost_basis=Decimal(0), cost_basis_local=Decimal(0))

@pytest.fixture
def existing_position_state() -> PositionState:
    """
    Returns a position state representing an existing holding, including dual-currency costs.
    Represents 100 shares with a base cost of $10,000 and a local cost of €9,000.
    """
    return PositionState(
        quantity=Decimal("100"), 
        cost_basis=Decimal("10000"), 
        cost_basis_local=Decimal("9000")
    )

def test_calculate_next_position_buy_from_zero(zero_position_state):
    """Tests a BUY transaction starting from no position."""
    buy_transaction = TransactionEvent(
        transaction_id="T1", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime.now(), transaction_type="BUY", quantity=Decimal("50"),
        price=Decimal("110"), gross_transaction_amount=Decimal("5500"),
        trade_currency="EUR", currency="EUR",
        net_cost=Decimal("5505"),  # Cost in portfolio base currency (USD)
        net_cost_local=Decimal("5005") # Cost in instrument local currency (EUR)
    )

    new_state = PositionCalculator.calculate_next_position(zero_position_state, buy_transaction)

    assert new_state.quantity == Decimal("50")
    assert new_state.cost_basis == Decimal("5505")
    assert new_state.cost_basis_local == Decimal("5005")

def test_calculate_next_position_sell_partial(existing_position_state):
    """
    Tests a partial SELL from an existing position, verifying proportional reduction
    of both base and local cost basis.
    """
    sell_transaction = TransactionEvent(
        transaction_id="T2", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime.now(), transaction_type="SELL", quantity=Decimal("40"),
        price=Decimal("120"), gross_transaction_amount=Decimal("4800"),
        trade_currency="EUR", currency="EUR"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, sell_transaction)

    # Quantity should decrease by 40 (100 -> 60)
    assert new_state.quantity == Decimal("60")
    # Base cost basis should decrease by 40% (10000 * 0.4 = 4000). Remaining = 6000
    assert new_state.cost_basis == Decimal("6000")
    # Local cost basis should also decrease by 40% (9000 * 0.4 = 3600). Remaining = 5400
    assert new_state.cost_basis_local == Decimal("5400")

def test_calculate_next_position_sell_full(existing_position_state):
    """Tests a SELL that fully closes the position, zeroing out both cost basis values."""
    sell_transaction = TransactionEvent(
        transaction_id="T3", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime.now(), transaction_type="SELL", quantity=Decimal("100"),
        price=Decimal("120"), gross_transaction_amount=Decimal("12000"),
        trade_currency="EUR", currency="EUR"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, sell_transaction)

    assert new_state.quantity == Decimal("0")
    assert new_state.cost_basis == Decimal("0")
    assert new_state.cost_basis_local == Decimal("0")

def test_fee_transaction_decreases_cash_position(zero_position_state):
    """
    Tests that a FEE transaction correctly decreases a cash position. For cash,
    quantity and cost_basis are the same.
    """
    fee_transaction = TransactionEvent(
        transaction_id="T4", portfolio_id="P1", instrument_id="CASH", security_id="CASH",
        transaction_date=datetime.now(), transaction_type="FEE", quantity=Decimal("1"),
        price=Decimal("25"), gross_transaction_amount=Decimal("25"),
        trade_currency="USD", currency="USD"
    )

    new_state = PositionCalculator.calculate_next_position(zero_position_state, fee_transaction)

    # State should reflect a negative cash position
    assert new_state.quantity == Decimal("-25")
    assert new_state.cost_basis == Decimal("-25")
    assert new_state.cost_basis_local == Decimal("-25")

def test_deposit_transaction_increases_cash_position(zero_position_state):
    """
    Tests that a DEPOSIT transaction correctly increases a cash position's quantity and cost.
    """
    deposit_transaction = TransactionEvent(
        transaction_id="T_DEPOSIT", portfolio_id="P1", instrument_id="CASH", security_id="CASH",
        transaction_date=datetime.now(), transaction_type="DEPOSIT", quantity=Decimal("10000"),
        price=Decimal("1"), gross_transaction_amount=Decimal("10000"),
        trade_currency="USD", currency="USD"
    )

    new_state = PositionCalculator.calculate_next_position(zero_position_state, deposit_transaction)

    assert new_state.quantity == Decimal("10000")
    assert new_state.cost_basis == Decimal("10000")
    assert new_state.cost_basis_local == Decimal("10000")

def test_dividend_transaction_does_not_change_position(existing_position_state):
    """
    Tests that a DIVIDEND transaction does not change the quantity or cost basis of the position.
    This verifies the bug fix.
    """
    dividend_transaction = TransactionEvent(
        transaction_id="T5_DIV", portfolio_id="P1", instrument_id="I1", security_id="S1",
        transaction_date=datetime.now(), transaction_type="DIVIDEND", quantity=Decimal("0"),
        price=Decimal("0"), gross_transaction_amount=Decimal("50"),
        trade_currency="EUR", currency="EUR"
    )

    new_state = PositionCalculator.calculate_next_position(existing_position_state, dividend_transaction)

    # The new state should be identical to the original state
    assert new_state.quantity == existing_position_state.quantity
    assert new_state.cost_basis == existing_position_state.cost_basis
    assert new_state.cost_basis_local == existing_position_state.cost_basis_local