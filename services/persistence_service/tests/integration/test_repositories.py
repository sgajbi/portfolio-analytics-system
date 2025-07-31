# services/persistence_service/tests/integration/test_repositories.py
import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session

from portfolio_common.database_models import Instrument, Transaction as DBTransaction
from portfolio_common.events import InstrumentEvent, TransactionEvent

from services.persistence_service.app.repositories.instrument_repository import InstrumentRepository
from services.persistence_service.app.repositories.transaction_db_repo import TransactionDBRepository


# --- Fixtures for reusable data ---
@pytest.fixture
def instrument_event_buy():
    return InstrumentEvent(
        securityId="SEC_AAPL_001",
        name="Apple Inc. (Test)",
        isin="US0378331005",
        instrumentCurrency="USD",
        productType="Equity"
    )

@pytest.fixture
def instrument_event_update():
    return InstrumentEvent(
        securityId="SEC_AAPL_001",
        name="Apple Inc. (Updated)", # Name changed
        isin="US0378331005_NEW", # ISIN changed
        instrumentCurrency="USD",
        productType="Equity_Updated" # Product type changed
    )

# --- Integration Tests for InstrumentRepository ---

def test_instrument_repository_create_new_instrument(clean_db, db_engine):
    """
    Tests that a new instrument can be successfully created.
    """
    with Session(db_engine) as db:
        repo = InstrumentRepository(db)
        
        event = InstrumentEvent(
            securityId="TEST_SEC_NEW",
            name="Test New Instrument",
            isin="TESTISIN123",
            instrumentCurrency="SGD",
            productType="Bond"
        )
        
        repo.create_or_update_instrument(event)
        # No commit in repo, so we don't need one here for this specific implementation (UPSERT)
        
        # Verify by fetching directly from DB
        fetched_instrument = db.query(Instrument).filter_by(security_id="TEST_SEC_NEW").first()
        assert fetched_instrument.name == "Test New Instrument"


def test_instrument_repository_upsert_update_existing_instrument(clean_db, db_engine, instrument_event_buy, instrument_event_update):
    """
    Tests that an existing instrument is updated when an UPSERT event with the same security_id occurs.
    """
    with Session(db_engine) as db:
        repo = InstrumentRepository(db)

        # 1. Create the initial instrument
        initial_instrument = repo.create_or_update_instrument(instrument_event_buy)
        db.flush() # flush to get DB-generated fields like timestamps
        db.expunge(initial_instrument)

        # 2. Update with the new event
        repo.create_or_update_instrument(instrument_event_update)

        # Verify by fetching directly from DB
        fetched_instrument = db.query(Instrument).filter_by(security_id="SEC_AAPL_001").first()
        assert fetched_instrument.name == "Apple Inc. (Updated)"
        assert fetched_instrument.product_type == "Equity_Updated"
        assert fetched_instrument.isin == "US0378331005_NEW"
        assert fetched_instrument.created_at is not None
        assert fetched_instrument.updated_at > fetched_instrument.created_at


def test_instrument_repository_upsert_no_change_on_identical_event(clean_db, db_engine, instrument_event_buy):
    """
    Tests that an UPSERT event with identical data results in no effective change.
    """
    with Session(db_engine) as db:
        repo = InstrumentRepository(db)

        # 1. Create the initial instrument
        initial_instrument = repo.create_or_update_instrument(instrument_event_buy)
        db.flush()
        
        # 2. Call UPSERT with an identical event
        repo.create_or_update_instrument(instrument_event_buy)
        
        count_in_db = db.query(Instrument).filter_by(security_id="SEC_AAPL_001").count()
        assert count_in_db == 1

# --- Test for TransactionDBRepository ---
def test_transaction_repository_is_idempotent(clean_db, db_engine):
    """
    Tests that creating the same transaction twice does not result in duplicates.
    """
    with Session(db_engine) as db:
        repo = TransactionDBRepository(db)

        event = TransactionEvent(
            transaction_id="IDEMPOTENCY_TEST_01",
            portfolio_id="PORT_T1",
            instrument_id="INST_T1",
            security_id="SEC_T1",
            transaction_date=datetime(2025, 7, 31, 10, 0, 0),
            transaction_type="BUY",
            quantity=Decimal("100"),
            price=Decimal("10"),
            gross_transaction_amount=Decimal("1000"),
            trade_currency="USD",
            currency="USD",
        )

        # 1. Create the transaction for the first time
        repo.create_or_update_transaction(event)
        db.commit() # The caller (this test) is now responsible for commit

        count1 = db.query(DBTransaction).filter_by(transaction_id=event.transaction_id).count()
        assert count1 == 1

        # 2. Create the exact same transaction again
        repo.create_or_update_transaction(event)
        db.commit() # Should commit nothing new

        count2 = db.query(DBTransaction).filter_by(transaction_id=event.transaction_id).count()
        assert count2 == 1