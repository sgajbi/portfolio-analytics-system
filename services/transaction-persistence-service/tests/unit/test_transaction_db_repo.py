import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portfolio_common.database_models import Base
from portfolio_common.events import TransactionEvent
from app.repositories.transaction_db_repo import TransactionDBRepository

# Setup for an in-memory SQLite database for testing
engine = create_engine("sqlite:///:memory:")
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """
    Fixture to create a new database session for each test function.
    It creates all tables, yields the session, and then drops all tables.
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_create_transaction_success(db_session):
    """
    Tests that a new transaction is successfully created in the database.
    """
    repo = TransactionDBRepository(db=db_session)

    test_event = TransactionEvent(
        transaction_id="test_txn_001",
        portfolio_id="test_port_001",
        instrument_id="AAPL",
        security_id="SEC_AAPL",
        transaction_date=date(2025, 7, 21),
        transaction_type="BUY",
        quantity=10.0,
        price=150.0,
        gross_transaction_amount=1500.0,
        trade_currency="USD",
        currency="USD"
    )

    # Action: Create the transaction
    created_transaction = repo.create_or_update_transaction(test_event)

    # Assertions
    assert created_transaction is not None
    assert created_transaction.transaction_id == "test_txn_001"
    assert created_transaction.instrument_id == "AAPL"

    # Verify it's actually in the DB
    retrieved_transaction = repo.get_transaction_by_pk(
        transaction_id="test_txn_001",
        portfolio_id="test_port_001",
        instrument_id="AAPL",
        transaction_date=date(2025, 7, 21)
    )
    assert retrieved_transaction is not None
    assert retrieved_transaction.security_id == "SEC_AAPL"

def test_update_existing_transaction_skips(db_session):
    """
    Tests that attempting to create a transaction that already exists is skipped.
    """
    repo = TransactionDBRepository(db=db_session)

    test_event = TransactionEvent(
        transaction_id="test_txn_002",
        portfolio_id="test_port_002",
        instrument_id="GOOG",
        security_id="SEC_GOOG",
        transaction_date=date(2025, 7, 22),
        transaction_type="SELL",
        quantity=5.0,
        price=2000.0,
        gross_transaction_amount=10000.0,
        trade_currency="USD",
        currency="USD"
    )

    # Create the transaction the first time
    first_creation = repo.create_or_update_transaction(test_event)
    assert first_creation.quantity == 5.0

    # Attempt to create it again
    second_attempt = repo.create_or_update_transaction(test_event)

    # Assertion: The returned object should be the same as the first one
    assert second_attempt.id == first_creation.id