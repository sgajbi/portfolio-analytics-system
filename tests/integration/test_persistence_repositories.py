import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from psycopg2.errors import UniqueViolation # Import for specific error checks if needed, though UPSERT avoids this normally

# Import database models and repository from their absolute paths relative to the project root
from portfolio_common.database_models import Instrument, Portfolio, MarketPrice, FxRate
from portfolio_common.events import InstrumentEvent, PortfolioEvent, MarketPriceEvent, FxRateEvent
from portfolio_common.db import get_db_session

# Corrected Imports:
# Assuming the project root is added to PYTHONPATH, we can import like this:
from services.persistence_service.app.repositories.instrument_repository import InstrumentRepository
# Uncomment and correct these when adding tests for other repositories:
# from services.persistence_service.app.repositories.portfolio_repository import PortfolioRepository
# from services.persistence_service.app.repositories.market_price_repository import MarketPriceRepository
# from services.persistence_service.app.repositories.fx_rate_repository import FxRateRepository


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
    # Use a direct session from the db_connection fixture for this test function
    # In a real app, you'd use get_db_session dependency, but here for direct test control
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
    Tests that an UPSERT event with identical data results in no effective change (updated_at might still change depending on DB/SQLA, but data should be same).
    """
    with Session(db_connection) as db:
        repo = InstrumentRepository(db)

        # 1. Create the initial instrument
        initial_instrument = repo.create_or_update_instrument(instrument_event_buy)
        initial_updated_at = initial_instrument.updated_at
        db.expunge_all() # Detach

        # Give a small delay to ensure updated_at changes if touched by DB
        import time
        time.sleep(0.01) 

        # 2. Call UPSERT with an identical event
        same_event = InstrumentEvent(
            securityId="SEC_AAPL_001",
            name="Apple Inc. (Test)",
            isin="US0378331005",
            instrumentCurrency="USD",
            productType="Equity"
        )
        upserted_instrument = repo.create_or_update_instrument(same_event)

        assert upserted_instrument.security_id == initial_instrument.security_id
        assert upserted_instrument.name == initial_instrument.name
        assert upserted_instrument.isin == initial_instrument.isin
        assert upserted_instrument.product_type == initial_instrument.product_type
        assert upserted_instrument.created_at == initial_instrument.created_at
        # updated_at might be equal or slightly greater depending on DB precision and actual update.
        # The key is that the business data fields are unchanged.
        assert upserted_instrument.updated_at >= initial_updated_at 
        
        # Ensure no new record was created
        count_in_db = db.query(Instrument).filter_by(security_id="SEC_AAPL_001").count()
        assert count_in_db == 1