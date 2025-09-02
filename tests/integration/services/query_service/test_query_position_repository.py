# tests/integration/services/query_service/test_query_position_repository.py
import pytest
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Portfolio, Instrument, DailyPositionSnapshot, PositionState, Transaction, PositionHistory

from src.services.query_service.app.repositories.position_repository import PositionRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_test_data(db_engine):
    """Sets up a portfolio with a security having two position snapshots on different days."""
    with Session(db_engine) as session:
        # Create prerequisite data
        portfolio = Portfolio(portfolio_id="POS_REPO_TEST_01", base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f")
        instrument = Instrument(
            security_id="SEC_POS_TEST_01", name="TestSec", isin="XS1234567890",
            currency="USD", product_type="Stock", asset_class="Equity",
            sector="Technology", country_of_risk="US"
        )
        session.add_all([portfolio, instrument])
        session.flush()

        # Create the corresponding PositionState record
        position_state = PositionState(
            portfolio_id="POS_REPO_TEST_01",
            security_id="SEC_POS_TEST_01",
            epoch=0,
            watermark_date=date(2024, 1, 1),
            status='CURRENT'
        )
        session.add(position_state)

        # Create two snapshots for the same security on different days
        today = date.today()
        yesterday = today - timedelta(days=1)

        snapshot_yesterday = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=yesterday,
            quantity=Decimal("100"), cost_basis=Decimal("10000"), epoch=0
        )
        snapshot_today = DailyPositionSnapshot(
            portfolio_id="POS_REPO_TEST_01", security_id="SEC_POS_TEST_01", date=today,
            quantity=Decimal("110"), cost_basis=Decimal("11000"), epoch=0
        )
        session.add_all([snapshot_yesterday, snapshot_today])
        session.commit()
    
    return {"today": today, "yesterday": yesterday}

@pytest.fixture(scope="function")
def setup_held_since_data(db_engine):
    """Sets up a broken holding period (BUY -> SELL -> BUY) for a security."""
    portfolio_id = "HELD_SINCE_P1"
    security_id = "HELD_SINCE_S1"
    with Session(db_engine) as session:
        # Prerequisites
        session.add(Portfolio(portfolio_id=portfolio_id, base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"))
        session.add(Transaction(transaction_id="T1", portfolio_id=portfolio_id, security_id=security_id, instrument_id="I1", transaction_date=date(2025,1,1), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD"))
        session.add(Transaction(transaction_id="T2", portfolio_id=portfolio_id, security_id=security_id, instrument_id="I1", transaction_date=date(2025,1,1), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD"))
        session.add(Transaction(transaction_id="T3", portfolio_id=portfolio_id, security_id=security_id, instrument_id="I1", transaction_date=date(2025,1,1), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD"))
        session.commit()

        # History: Buy on Mar 1, Sell on Mar 15 (quantity -> 0), Buy again on Apr 1
        history = [
            PositionHistory(portfolio_id=portfolio_id, security_id=security_id, transaction_id="T1", epoch=0, position_date=date(2025, 3, 1), quantity=Decimal("100"), cost_basis=Decimal("1000")),
            PositionHistory(portfolio_id=portfolio_id, security_id=security_id, transaction_id="T2", epoch=0, position_date=date(2025, 3, 15), quantity=Decimal("0"), cost_basis=Decimal("0")),
            PositionHistory(portfolio_id=portfolio_id, security_id=security_id, transaction_id="T3", epoch=0, position_date=date(2025, 4, 1), quantity=Decimal("50"), cost_basis=Decimal("550")),
        ]
        session.add_all(history)
        session.commit()


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

    latest_snapshot, instrument, pos_state = latest_positions[0]
    
    assert latest_snapshot.portfolio_id == portfolio_id
    assert latest_snapshot.security_id == "SEC_POS_TEST_01"
    assert latest_snapshot.date == setup_test_data["today"]
    assert latest_snapshot.quantity == Decimal("110")
    assert instrument.name == "TestSec"
    assert pos_state.status == "CURRENT"
    assert instrument.asset_class == "Equity"
    assert instrument.isin == "XS1234567890"
    assert instrument.currency == "USD"
    assert instrument.sector == "Technology"
    assert instrument.country_of_risk == "US"
    assert latest_snapshot.epoch == 0

async def test_get_held_since_date(clean_db, setup_held_since_data, async_db_session: AsyncSession):
    """
    GIVEN a position history with a period of zero quantity
    WHEN get_held_since_date is called
    THEN it should return the date of the first transaction that re-opened the position.
    """
    # ARRANGE
    repo = PositionRepository(async_db_session)
    portfolio_id = "HELD_SINCE_P1"
    security_id = "HELD_SINCE_S1"

    # ACT
    held_since = await repo.get_held_since_date(portfolio_id, security_id, 0)

    # ASSERT
    # The last zero quantity was on Mar 15. The next transaction was on Apr 1.
    assert held_since == date(2025, 4, 1)