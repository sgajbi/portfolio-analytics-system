# tests/integration/services/query_service/test_query_position_repository.py
import pytest
from datetime import date, timedelta
from decimal import Decimal

# Use the synchronous engine for test setup, as it's simpler.
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Portfolio, Instrument, DailyPositionSnapshot, PositionState

# CORRECTED IMPORT: Now points to the query_service's repository
from src.services.query_service.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_test_data(db_engine):
    """Sets up a portfolio with a security having two position snapshots on different days."""
    with Session(db_engine) as session:
        # Create prerequisite data
        portfolio = Portfolio(portfolio_id="POS_REPO_TEST_01", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f")
        instrument = Instrument(security_id="SEC_POS_TEST_01", name="TestSec", isin="XS123", currency="USD", product_type="Stock", asset_class="Equity") # ADDED: asset_class
        session.add_all([portfolio, instrument])
        session.flush()

        # --- NEW: Create the corresponding PositionState record ---
        # The query now depends on this record existing to find the latest epoch.
        position_state = PositionState(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            epoch=0, # Snapshots will have default epoch of 0
            watermark_date=date(2024, 1, 1),
            status='CURRENT'
        )
        session.add(position_state)
        # --- END NEW ---

        # Create two snapshots for the same security on different days
        today = date.today()
        yesterday = today - timedelta(days=1)

        snapshot_yesterday = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=yesterday,
            quantity=Decimal("100"), cost_basis=Decimal("10000"), epoch=0 # Explicitly set epoch
        )
        snapshot_today = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=today,
            quantity=Decimal("110"), cost_basis=Decimal("11000"), epoch=0 # Explicitly set epoch
        )
        session.add_all([snapshot_yesterday, snapshot_today])
        session.commit()
    
    return {"today": today, "yesterday": yesterday}


async def test_get_latest_positions_by_portfolio(clean_db, setup_test_data, async_db_session: AsyncSession):
    """
    GIVEN a security with multiple historical daily snapshots in the database
    WHEN get_latest_positions_by_portfolio is called
    THEN it should return only the single, most recent snapshot for that security.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "POS_REPO_TEST_01"

    # ACT
    latest_positions = await repo.get_latest_positions_by_portfolio(portfolio_id)

    # ASSERT
    assert len(latest_positions) == 1

    # UPDATED: Unpack the new asset_class field
    latest_snapshot, instrument_name, reprocessing_status, asset_class = latest_positions[0]
    
    assert latest_snapshot.portfolio_id == portfolio_id
    assert latest_snapshot.security_id == "SEC_POS_TEST_01"
    assert latest_snapshot.date == setup_test_data["today"]
    assert latest_snapshot.quantity == Decimal("110")
    assert instrument_name == "TestSec"
    assert reprocessing_status == "CURRENT"
    assert asset_class == "Equity" # VERIFY: New field is returned