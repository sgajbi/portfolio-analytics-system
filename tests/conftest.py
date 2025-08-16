# tests/conftest.py
import pytest
import requests
import time
import subprocess
import os
from testcontainers.compose import DockerCompose
import sys
# UPDATED IMPORTS
from sqlalchemy import create_engine, text
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def docker_services(request):
    """
    A session-scoped fixture that starts the Docker Compose stack and waits for the
    ingestion_service to become healthy before yielding to the tests.
    """
    compose = DockerCompose(".", compose_file_name="docker-compose.yml")
    with compose:
        print("\n--- Waiting for services to become healthy ---")

        host = compose.get_service_host("ingestion_service", 8000)
        port = compose.get_service_port("ingestion_service", 8000)
        health_url = f"http://{host}:{port}/health/ready"
        
        start_time = time.time()
        timeout = 180
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url)
                if response.status_code == 200:
                    print(f"Ingestion service is ready at {health_url}")
                    break
            except requests.ConnectionError:
                time.sleep(2)
        else:
            pytest.fail(f"Ingestion service did not become ready within {timeout} seconds.")
            
        yield compose

@pytest.fixture(scope="session")
def db_engine(docker_services: DockerCompose):
    """
    A session-scoped fixture that provides a SQLAlchemy Engine.
    The engine is created only once for the entire test session for efficiency.
    """
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    url = f"postgresql://{os.getenv('POSTGRES_USER', 'user')}:{os.getenv('POSTGRES_PASSWORD', 'password')}@{host}:{port}/{os.getenv('POSTGRES_DB', 'portfolio_db')}"
    engine = create_engine(url)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    A function-scoped fixture that cleans all data from tables using TRUNCATE,
    leaving the schema intact. This is much faster and more reliable than
    dropping tables or running alembic downgrade/upgrade.
    """
    print("\n--- Cleaning database tables ---")

    TABLES = [
        "portfolio_valuation_jobs", "portfolio_aggregation_jobs", "transaction_costs", "cashflows", "position_history", "daily_position_snapshots",
        "position_timeseries", "portfolio_timeseries", "transactions", "market_prices",
        "instruments", "fx_rates", "portfolios", "processed_events", "outbox_events"
    ]
    
    truncate_query = text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE;")

    with db_engine.begin() as connection:
        connection.execute(truncate_query)
    
    print("--- Database tables cleaned ---")
    yield

@pytest_asyncio.fixture(scope="function")
async def async_db_session(db_engine):
    """
    A function-scoped async fixture that provides a SQLAlchemy AsyncSession
    connected to the test database. Ensures the engine and session are
    created and torn down within the active asyncio event loop of the test.
    """
    sync_url = db_engine.url
    async_url = sync_url.render_as_string(hide_password=False).replace(
        "postgresql://", "postgresql+asyncpg://"
    )

    async_engine = create_async_engine(async_url)
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with AsyncSessionLocal() as session:
        yield session

    await async_engine.dispose()