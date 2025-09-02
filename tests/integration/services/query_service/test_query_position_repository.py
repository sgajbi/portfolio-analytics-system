# tests/integration/services/query_service/test_query_position_repository.py
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.position_repository import PositionRepository
from portfolio_common.database_models import DailyPositionSnapshot, PositionState, Instrument, PositionHistory

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module", autouse=True)
async def setup_test_data(async_db_session: AsyncSession):
    """
    Sets up the necessary data for the position repository tests.
    Inserts instrument, position state, and multiple daily snapshots.
    """
    today = date(2025, 9, 2)
    yesterday = date(2025, 9, 1)
    portfolio_id = "POS_REPO_TEST_01"
    security_id = "SEC_01"
    
    # Create an instrument record
    instrument = Instrument(
        security_id=security_id, name="Test Bond", isin="TESTISIN", currency="USD",
        asset_class="Fixed Income", sector="Government", country_of_risk="US",
        issuer_id="USA_GOV", ultimate_parent_issuer_id="USA_GOV"
    )
    
    # Create the current state for this position
    state = PositionState(portfolio_id=portfolio_id, security_id=security_id, epoch=1, status="CURRENT")
    
    # Create historical snapshots
    snapshot_yesterday = DailyPositionSnapshot(
        portfolio_id=portfolio_id, security_id=security_id, epoch=1, date=yesterday,
        quantity=Decimal("100"), cost_basis=Decimal("10000"), market_value=Decimal("10100")
    )
    snapshot_today = DailyPositionSnapshot(
        portfolio_id=portfolio_id, security_id=security_id, epoch=1, date=today,
        quantity=Decimal("100"), cost_basis=Decimal("10000"), market_value=Decimal("10200")
    )

    # A snapshot from a previous, now-inactive epoch that should be ignored
    stale_snapshot = DailyPositionSnapshot(
        portfolio_id=portfolio_id, security_id=security_id, epoch=0, date=today,
        quantity=Decimal("50"), cost_basis=Decimal("5000"), market_value=Decimal("5500")
    )
    
    # Position history for held-since calculation
    history_start = PositionHistory(
        portfolio_id=portfolio_id, security_id=security_id, epoch=1,
        position_date=date(2025, 8, 1), quantity=Decimal("100")
    )
    
    async_db_session.add_all([
        instrument, state, snapshot_yesterday, snapshot_today, stale_snapshot, history_start
    ])
    await async_db_session.commit()
    
    yield {"today": today, "yesterday": yesterday}

async def test_get_latest_positions_by_portfolio(clean_db, setup_test_data, async_db_session: AsyncSession):
    """
    GIVEN a security with multiple historical daily snapshots in the database
    WHEN get_latest_positions_by_portfolio is called
    THEN it should return only the single, most recent snapshot for that security, including all instrument data.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "POS_REPO_TEST_01"

    # ACT
    latest_positions = await repo.get_latest_positions_by_portfolio(portfolio_id)

    # ASSERT
    assert len(latest_positions) == 1

    # Unpack all the returned columns
    (
        latest_snapshot, instrument_name, reprocessing_status, isin,
        currency, asset_class, sector, country_of_risk, issuer_id,
        parent_issuer_id, epoch
    ) = latest_positions[0]

    # Check the snapshot data is the latest one
    assert latest_snapshot.date == setup_test_data["today"]
    assert latest_snapshot.market_value == Decimal("10200")
    assert latest_snapshot.epoch == 1 # Belongs to the current epoch
    
    # Check that the joined instrument data is correct
    assert instrument_name == "Test Bond"
    assert asset_class == "Fixed Income"
    assert reprocessing_status == "CURRENT"
    assert issuer_id == "USA_GOV"
    assert parent_issuer_id == "USA_GOV"

async def test_get_held_since_date(clean_db, setup_test_data, async_db_session: AsyncSession):
    """
    GIVEN position history for a security
    WHEN get_held_since_date is called
    THEN it should return the earliest date of the continuous holding period.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "POS_REPO_TEST_01"
    security_id = "SEC_01"
    epoch = 1

    # ACT
    held_since = await repo.get_held_since_date(portfolio_id, security_id, epoch)
    
    # ASSERT
    assert held_since == date(2025, 8, 1)