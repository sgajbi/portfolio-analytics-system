# tests/unit/test_sorter.py

import pytest
from datetime import date, datetime
from decimal import Decimal
from src.core.models.transaction import Transaction
from src.logic.sorter import TransactionSorter

@pytest.fixture
def sorter():
    return TransactionSorter()

def test_sort_by_date(sorter):
    t1 = Transaction(transaction_id="t1", transaction_date=datetime(2023, 1, 5), quantity=1, portfolio_id="P1", instrument_id="A", security_id="S1", transaction_type="BUY", settlement_date=datetime(2023, 1, 5), gross_transaction_amount=1, trade_currency="USD")
    t2 = Transaction(transaction_id="t2", transaction_date=datetime(2023, 1, 1), quantity=1, portfolio_id="P1", instrument_id="A", security_id="S1", transaction_type="BUY", settlement_date=datetime(2023, 1, 1), gross_transaction_amount=1, trade_currency="USD")
    sorted_list = sorter.sort_transactions([], [t1, t2])
    assert [t.transaction_id for t in sorted_list] == ["t2", "t1"]