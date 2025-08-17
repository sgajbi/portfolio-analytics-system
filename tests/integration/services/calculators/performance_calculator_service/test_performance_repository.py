# tests/integration/services/calculators/performance_calculator_service/test_performance_repository.py
import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from portfolio_common.database_models import Portfolio, DailyPerformanceMetric
from src.services.calculators.performance_calculator_service.app.repositories.performance_repository import PerformanceRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
def setup_portfolio(db_engine):
    """Sets up a prerequisite portfolio for the test."""
    with Session(db_engine) as session:
        portfolio = Portfolio(
            portfolio_id="PERF_REPO_TEST_01", base_currency="USD", open_date=date(2024,1,1),
            risk_exposure="a", investment_time_horizon="b", portfolio_type="c",
            booking_center="d", cif_id="e", status="f"
        )
        session.add(portfolio)
        session.commit()

async def test_upsert_daily_metrics_inserts_and_updates(
    clean_db, setup_portfolio, async_db_session: AsyncSession
):
    """
    GIVEN a list of new and updated performance metrics
    WHEN upsert_daily_metrics is called
    THEN it should insert new records and update existing ones correctly.
    """
    # ARRANGE
    repo = PerformanceRepository(async_db_session)
    test_date = date(2025, 8, 15)
    portfolio_id = "PERF_REPO_TEST_01"

    # 1. Initial Insert
    initial_metrics = [
        DailyPerformanceMetric(
            portfolio_id=portfolio_id, date=test_date, return_basis="NET",
            linking_factor=Decimal("1.01"), daily_return_pct=Decimal("1.0")
        ),
        DailyPerformanceMetric(
            portfolio_id=portfolio_id, date=test_date, return_basis="GROSS",
            linking_factor=Decimal("1.02"), daily_return_pct=Decimal("2.0")
        ),
    ]
    await repo.upsert_daily_metrics(initial_metrics)
    await async_db_session.commit()

    # ASSERT 1: Verify initial insert
    stmt1 = select(DailyPerformanceMetric).where(DailyPerformanceMetric.portfolio_id == portfolio_id)
    result1 = await async_db_session.execute(stmt1)
    records1 = result1.scalars().all()
    assert len(records1) == 2
    assert records1[0].linking_factor == Decimal("1.01")

    # 2. Update existing records
    updated_metrics = [
        DailyPerformanceMetric(
            portfolio_id=portfolio_id, date=test_date, return_basis="NET",
            linking_factor=Decimal("1.03"), daily_return_pct=Decimal("3.0")
        )
    ]
    await repo.upsert_daily_metrics(updated_metrics)
    await async_db_session.commit()

    # ASSERT 2: Verify the update
    stmt2 = select(DailyPerformanceMetric).where(
        DailyPerformanceMetric.portfolio_id == portfolio_id,
        DailyPerformanceMetric.return_basis == "NET"
    )
    result2 = await async_db_session.execute(stmt2)
    updated_record = result2.scalars().one()
    assert updated_record.linking_factor == Decimal("1.03")
    
    # Verify the gross record was not affected
    stmt3 = select(DailyPerformanceMetric).where(
        DailyPerformanceMetric.portfolio_id == portfolio_id,
        DailyPerformanceMetric.return_basis == "GROSS"
    )
    result3 = await async_db_session.execute(stmt3)
    gross_record = result3.scalars().one()
    assert gross_record.linking_factor == Decimal("1.02")