# tests/integration/services/recalculation_service/test_recalculation_repository.py
import pytest
from unittest.mock import AsyncMock
from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.database_models import (
    Portfolio, Instrument, Transaction, RecalculationJob,
    PositionHistory, DailyPositionSnapshot, PositionTimeseries,
    PortfolioTimeseries, Cashflow
)
from src.services.recalculation_service.app.repositories.recalculation_repository import RecalculationRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_recalc_job_data(db_engine, clean_db):
    """
    Sets up a PENDING and a PROCESSING job for testing the claim logic.
    """
    with Session(db_engine) as session:
        session.add_all([
            RecalculationJob(portfolio_id="P1", security_id="S1", from_date=date(2025, 8, 1), status="PENDING"),
            RecalculationJob(portfolio_id="P2", security_id="S2", from_date=date(2025, 8, 1), status="PROCESSING"),
        ])
        session.commit()

@pytest.fixture(scope="function")
def setup_full_downstream_data(db_engine, clean_db):
    """
    Creates a full set of dependent data for a single security to test cascading deletes.
    """
    portfolio_id = "RECALC_DEL_P1"
    security_id = "RECALC_DEL_S1"
    date_before = date(2025, 8, 10)
    date_after = date(2025, 8, 12)

    with Session(db_engine) as session:
        session.add_all([
            Portfolio(portfolio_id=portfolio_id, base_currency="USD", open_date=date(2024,1,1), risk_exposure="a", investment_time_horizon="b", portfolio_type="c", booking_center="d", cif_id="e", status="f"),
            Instrument(security_id=security_id, name="Test", isin="XS1", currency="USD", product_type="Stock")
        ])
        session.flush()

        session.add(Transaction(transaction_id="T1", portfolio_id=portfolio_id, instrument_id="I1", security_id=security_id, transaction_date=datetime(2025,8,10), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD"))
        session.add(Transaction(transaction_id="T2", portfolio_id=portfolio_id, instrument_id="I1", security_id=security_id, transaction_date=datetime(2025,8,12), transaction_type="BUY", quantity=1, price=1, gross_transaction_amount=1, trade_currency="USD", currency="USD"))
        session.flush()

        session.add_all([
            PositionHistory(portfolio_id=portfolio_id, security_id=security_id, transaction_id="T1", position_date=date_before, quantity=1, cost_basis=1),
            PositionHistory(portfolio_id=portfolio_id, security_id=security_id, transaction_id="T2", position_date=date_after, quantity=2, cost_basis=2),
            DailyPositionSnapshot(portfolio_id=portfolio_id, security_id=security_id, date=date_before, quantity=1, cost_basis=1),
            DailyPositionSnapshot(portfolio_id=portfolio_id, security_id=security_id, date=date_after, quantity=2, cost_basis=2),
            PositionTimeseries(portfolio_id=portfolio_id, security_id=security_id, date=date_before, bod_market_value=0, bod_cashflow_position=0, eod_cashflow_position=0, bod_cashflow_portfolio=0, eod_cashflow_portfolio=0, eod_market_value=0, fees=0, quantity=0, cost=0),
            PositionTimeseries(portfolio_id=portfolio_id, security_id=security_id, date=date_after, bod_market_value=0, bod_cashflow_position=0, eod_cashflow_position=0, bod_cashflow_portfolio=0, eod_cashflow_portfolio=0, eod_market_value=0, fees=0, quantity=0, cost=0),
            PortfolioTimeseries(portfolio_id=portfolio_id, date=date_before, bod_market_value=0, bod_cashflow=0, eod_cashflow=0, eod_market_value=0, fees=0),
            PortfolioTimeseries(portfolio_id=portfolio_id, date=date_after, bod_market_value=0, bod_cashflow=0, eod_cashflow=0, eod_market_value=0, fees=0),
            Cashflow(transaction_id="T1", portfolio_id=portfolio_id, security_id=security_id, cashflow_date=date_before, amount=1, currency="USD", classification="A", timing="BOD", calculation_type="NET"),
            Cashflow(transaction_id="T2", portfolio_id=portfolio_id, security_id=security_id, cashflow_date=date_after, amount=1, currency="USD", classification="A", timing="BOD", calculation_type="NET")
        ])
        session.commit()

    return {"portfolio_id": portfolio_id, "security_id": security_id, "from_date": date(2025, 8, 11)}

async def test_find_and_claim_job(db_engine, clean_db, setup_recalc_job_data, async_db_session: AsyncSession):
    # ARRANGE
    repo = RecalculationRepository(async_db_session)
    
    # ACT
    job = await repo.find_and_claim_job()
    await async_db_session.commit()

    # ASSERT
    assert job is not None
    assert job.status == "PROCESSING"
    assert job.portfolio_id == "P1"

async def test_delete_downstream_data(db_engine, clean_db, setup_full_downstream_data, async_db_session: AsyncSession):
    # ARRANGE
    repo = RecalculationRepository(async_db_session)
    params = setup_full_downstream_data

    # ACT
    await repo.delete_downstream_data(
        params["portfolio_id"], params["security_id"], params["from_date"]
    )
    await async_db_session.commit()

    # ASSERT
    with Session(db_engine) as session:
        assert session.query(PositionHistory).where(PositionHistory.position_date >= params["from_date"]).count() == 0
        assert session.query(DailyPositionSnapshot).where(DailyPositionSnapshot.date >= params["from_date"]).count() == 0
        assert session.query(PositionTimeseries).where(PositionTimeseries.date >= params["from_date"]).count() == 0
        assert session.query(PortfolioTimeseries).where(PortfolioTimeseries.date >= params["from_date"]).count() == 0
        assert session.query(Cashflow).where(Cashflow.cashflow_date >= params["from_date"]).count() == 0
        
        # Verify that data BEFORE the from_date remains untouched
        assert session.query(Cashflow).count() == 1