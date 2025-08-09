# tests/unit/test_disposition_engine.py

import pytest
from datetime import date, datetime
from decimal import Decimal

from logic.disposition_engine import DispositionEngine
from logic.cost_basis_strategies import FIFOBasisStrategy, AverageCostBasisStrategy
from core.models.transaction import Transaction
from core.enums.transaction_type import TransactionType

@pytest.fixture
def fifo_engine():
    return DispositionEngine(cost_basis_strategy=FIFOBasisStrategy())

@pytest.fixture
def avco_engine():
    return DispositionEngine(cost_basis_strategy=AverageCostBasisStrategy())

@pytest.fixture
def buy_transaction():
    return Transaction(
        transaction_id="B1", portfolio_id="P1", instrument_id="A", security_id="S1",
        transaction_type=TransactionType.BUY, transaction_date=datetime(2023, 1, 1), settlement_date=datetime(2023, 1, 3),
        quantity=Decimal("10"), gross_transaction_amount=Decimal("100"), net_cost=Decimal("105"),
        trade_currency="USD",
        # --- FIX: Add required fields ---
        portfolio_base_currency="USD", net_cost_local=Decimal("105")
    )

def test_add_buy_lot(fifo_engine, buy_transaction):
    fifo_engine.add_buy_lot(buy_transaction)
    assert fifo_engine.get_available_quantity("P1", "A") == Decimal("10")