# tests/integration/services/calculators/performance_calculator_service/test_performance_repository.py
import pytest
import pytest_asyncio
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
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

@pytest_asyncio.fixture(scope="function")
async def session_factory(db_engine):
    """Provides a factory for creating new, isolated AsyncSessions for the test."""
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://"
    )
    async_engine = create_async_engine(async_url)
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory
    await async_engine.dispose()


async def test_upsert_daily_metrics_inserts_and_updates(
    clean_db, setup_portfolio, session_factory: async_sessionmaker
):
    """
    GIVEN a list of new and updated performance metrics
    WHEN upsert_daily_metrics is called in separate transactions
    THEN it should insert new records and update existing ones correctly.
    """
    test_date = date(2025, 8, 15)
    portfolio_id = "PERF_REPO_TEST_01"

    # --- Step 1: Initial Insert ---
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
    
    async with session_factory() as session:
        repo = PerformanceRepository(session)
        await repo.upsert_daily_metrics(initial_metrics)
        await session.commit()

    # --- Step 2: Verify Initial Insert in a New Session ---
    async with session_factory() as session:
        stmt1 = select(DailyPerformanceMetric).where(DailyPerformanceMetric.portfolio_id == portfolio_id).order_by(DailyPerformanceMetric.return_basis)
        result1 = await session.execute(stmt1)
        records1 = result1.scalars().all()
        assert len(records1) == 2
        assert records1[1].linking_factor == Decimal("1.01") # NET
        assert records1[0].linking_factor == Decimal("1.02") # GROSS

    # --- Step 3: Update existing records ---
    updated_metrics = [
        DailyPerformanceMetric(
            portfolio_id=portfolio_id, date=test_date, return_basis="NET",
            linking_factor=Decimal("1.03"), daily_return_pct=Decimal("3.0")
        )
    ]

    async with session_factory() as session:
        repo = PerformanceRepository(session)
        await repo.upsert_daily_metrics(updated_metrics)
        await session.commit()

    # --- Step 4: Verify the update in a final, clean session ---
    async with session_factory() as session:
        stmt2 = select(DailyPerformanceMetric).where(
            DailyPerformanceMetric.portfolio_id == portfolio_id,
            DailyPerformanceMetric.return_basis == "NET"
        )
        result2 = await session.execute(stmt2)
        updated_record = result2.scalars().one()
        assert updated_record.linking_factor == Decimal("1.03")

        # Verify the other record was untouched
        stmt3 = select(DailyPerformanceMetric).where(
            DailyPerformanceMetric.portfolio_id == portfolio_id,
            DailyPerformanceMetric.return_basis == "GROSS"
        )
        result3 = await session.execute(stmt3)
        gross_record = result3.scalars().one()
        assert gross_record.linking_factor == Decimal("1.02")