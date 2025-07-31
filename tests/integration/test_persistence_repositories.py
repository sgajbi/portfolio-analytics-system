# tests/integration/test_persistence_repositories.py
import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session

# Import database models and event DTOs from portfolio_common
from portfolio_common.database_models import Instrument, Transaction as DBTransaction
from portfolio_common.events import InstrumentEvent, TransactionEvent

# Corrected Local Imports: These now work because 'services/persistence-service'
# is on the pythonpath, making 'app' a top-level module for the tests.
from app.repositories.instrument_repository import InstrumentRepository
from app.repositories.transaction_db_repo import TransactionDBRepository


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

def test_instrument_repository_create_new_instrument(clean_db, db_connection):
    """
    Tests that a new instrument can be successfully created.
    """
    with Session(db_connection) as db:
        repo = InstrumentRepository(db)
        
        event = InstrumentEvent(
            securityId="TEST_SEC_NEW",
            name="Test New Instrument",
            isin="TESTISIN123",
            instrumentCurrency="SGD",
            productType="Bond"
        )
        
        created_instrument = repo.create_or_update_instrument(event)
        
        assert created_instrument is not None
        assert created_instrument.security_id == "TEST_SEC_NEW"
        assert created_instrument.name == "Test New Instrument"
        
        # Verify by fetching directly from DB
        fetched_instrument = db.query(Instrument).filter_by(security_id="TEST_SEC_NEW").first()
        assert fetched_instrument.name == "Test New Instrument"


def test_instrument_repository_upsert_update_existing_instrument(clean_db, db_connection, instrument_event_buy, instrument_event_update):
    """
    Tests that an existing instrument is updated when an UPSERT event with the same security_id occurs.
    """
    with Session(db_connection) as db:
        repo = InstrumentRepository(db)

        # 1. Create the initial instrument
        initial_instrument = repo.create_or_update_instrument(instrument_event_buy)
        assert initial_instrument.name == "Apple Inc. (Test)"
        assert initial_instrument.product_type == "Equity"
        db.expunge_all() # Detach the object from the session to ensure we query fresh later

        # 2. Update with the new event
        updated_instrument = repo.create_or_update_instrument(instrument_event_update)

        assert updated_instrument is not None
        assert updated_instrument.security_id == "SEC_AAPL_001"
        assert updated_instrument.name == "Apple Inc. (Updated)" # Should be updated
        assert updated_instrument.product_type == "Equity_Updated" # Should be updated
        assert updated_instrument.isin == "US0378331005_NEW" # Should be updated

        # Verify by fetching directly from DB
        fetched_instrument = db.query(Instrument).filter_by(security_id="SEC_AAPL_001").first()
        assert fetched_instrument.name == "Apple Inc. (Updated)"
        assert fetched_instrument.product_type == "Equity_Updated"
        assert fetched_instrument.isin == "US0378331005_NEW"
        assert fetched_instrument.created_at == initial_instrument.created_at # created_at should not change
        assert fetched_instrument.updated_at > initial_instrument.updated_at # updated_at should change


def test_instrument_repository_upsert_no_change_on_identical_event(clean_db, db_connection, instrument_event_buy):
    """
    Tests that an UPSERT event with identical data results in no effective change.
    """
    with Session(db_connection) as db:
        repo = InstrumentRepository(db)

        # 1. Create the initial instrument
        initial_instrument = repo.create_or_update_instrument(instrument_event_buy)
        initial_updated_at = initial_instrument.updated_at
        db.expunge_all() # Detach

        # 2. Call UPSERT with an identical event
        same_event = InstrumentEvent(
            securityId="SEC_AAPL_001",
            name="Apple Inc. (Test)",
            isin="US0378331005",
            instrumentCurrency="USD",
            productType="Equity"
        )
        upserted_instrument = repo.create_or_update_instrument(same_event)

        assert upserted_instrument.name == initial_instrument.name
        # The key is that the business data fields are unchanged.
        assert upserted_instrument.updated_at >= initial_updated_at 
        
        # Ensure no new record was created
        count_in_db = db.query(Instrument).filter_by(security_id="SEC_AAPL_001").count()
        assert count_in_db == 1

# --- NEW: Test for TransactionDBRepository ---
def test_transaction_repository_is_idempotent(clean_db, db_connection):
    """
    Tests that creating the same transaction twice does not result in duplicates.
    This validates the core idempotency requirement before we refactor.
    """
    with Session(db_connection) as db:
        repo = TransactionDBRepository(db)

        # Define a sample transaction event
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

        # Verify it was created
        count1 = db.query(DBTransaction).filter_by(transaction_id=event.transaction_id).count()
        assert count1 == 1

        # 2. Create the exact same transaction again
        repo.create_or_update_transaction(event)

        # Verify that the count is still 1
        count2 = db.query(DBTransaction).filter_by(transaction_id=event.transaction_id).count()
        assert count2 == 1