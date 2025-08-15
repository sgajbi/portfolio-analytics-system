# tests/integration/services/query_service/test_position_repository.py
import pytest
from datetime import date, timedelta
from decimal import Decimal

# Use the synchronous engine for test setup, as it's simpler.
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Portfolio, Instrument, DailyPositionSnapshot

from src.services.calculators.position_calculator.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_test_data(db_engine):
    """Sets up a portfolio with a security having two position snapshots on different days."""
    with Session(db_engine) as session:
        # Create prerequisite data
        portfolio = Portfolio(portfolio_id="POS_REPO_TEST_01", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f")
        instrument = Instrument(security_id="SEC_POS_TEST_01", name="TestSec", isin="XS123", currency="USD", product_type="Stock")
        session.add_all([portfolio, instrument])
        session.flush()

        # Create two snapshots for the same security on different days
        today = date.today()
        yesterday = today - timedelta(days=1)

        snapshot_yesterday = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=yesterday,
            quantity=Decimal("100"), cost_basis=Decimal("10000")
        )
        snapshot_today = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=today,
            quantity=Decimal("110"), cost_basis=Decimal("11000")
        )
        session.add_all([snapshot_yesterday, snapshot_today])
        session.commit()
    return {"today": today, "yesterday": yesterday}

@pytest.fixture(scope="function")
def setup_open_positions_data(db_engine):
    """
    Sets up a portfolio with multiple securities, where some positions are open and some are closed.
    """
    with Session(db_engine) as session:
        portfolio = Portfolio(portfolio_id="OPEN_POS_TEST_01", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f")
        session.add(portfolio)
        session.flush()

        snapshots = [
            # S1: Open position
            DailyPositionSnapshot(portfolio_id="OPEN_POS_TEST_01", security_id="S1_OPEN", date=date(2025, 8, 1), quantity=Decimal("100"), cost_basis=Decimal("1")),
            # S2: Closed position
            DailyPositionSnapshot(portfolio_id="OPEN_POS_TEST_01", security_id="S2_CLOSED", date=date(2025, 8, 2), quantity=Decimal("50"), cost_basis=Decimal("1")),
            DailyPositionSnapshot(portfolio_id="OPEN_POS_TEST_01", security_id="S2_CLOSED", date=date(2025, 8, 3), quantity=Decimal("0"), cost_basis=Decimal("0")),
            # S3: Open position, snapshot is old but it's the latest
            DailyPositionSnapshot(portfolio_id="OPEN_POS_TEST_01", security_id="S3_OPEN_OLD", date=date(2025, 7, 15), quantity=Decimal("200"), cost_basis=Decimal("1")),
        ]
        session.add_all(snapshots)
        session.commit()

async def test_find_open_security_ids_as_of(clean_db, setup_open_positions_data, async_db_session: AsyncSession):
    """
    GIVEN a portfolio with a mix of open and closed positions
    WHEN find_open_security_ids_as_of is called
    THEN it should return only the security IDs of the open positions.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "OPEN_POS_TEST_01"
    as_of_date = date(2025, 8, 5)

    # ACT
    open_security_ids = await repo.find_open_security_ids_as_of(portfolio_id, as_of_date)

    # ASSERT
    assert len(open_security_ids) == 2
    assert "S1_OPEN" in open_security_ids
    assert "S3_OPEN_OLD" in open_security_ids
    assert "S2_CLOSED" not in open_security_ids


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

    # The result is a Row object, where the first element is the snapshot
    latest_snapshot = latest_positions[0][0]
    
    assert latest_snapshot.portfolio_id == portfolio_id
    assert latest_snapshot.security_id == "SEC_POS_TEST_01"
    assert latest_snapshot.date == setup_test_data["today"]
    assert latest_snapshot.quantity == Decimal("110")