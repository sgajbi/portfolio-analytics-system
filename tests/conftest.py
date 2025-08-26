# tests/conftest.py
import pytest
import requests
import time
import subprocess
import os
import sys
from sqlalchemy import create_engine, text, exc
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from typing import Callable, Any

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# REFACTORED: Use subprocess directly for more control over Docker Compose
@pytest.fixture(scope="session")
def docker_services(request):
    """
    Starts the Docker Compose stack using subprocess and waits for services to be healthy.
    This provides more control and resilience than the default testcontainers behavior.
    """
    compose_file = os.path.join(project_root, "docker-compose.yml")
    
    try:
        # Use --build to ensure images are up-to-date and -d to run in the background
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "up", "--build", "-d"], 
            check=True, capture_output=True
        )
        
        # Manual polling for service health
        print("\n--- Waiting for API services to become healthy ---")
        services_to_check = {
            "ingestion_service": "http://localhost:8000/health/ready",
            "query_service": "http://localhost:8001/health/ready"
        }
        timeout = 180
        
        for service_name, health_url in services_to_check.items():
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = requests.get(health_url, timeout=2)
                    if response.status_code == 200:
                        print(f"--- Service '{service_name}' is healthy at {health_url} ---")
                        break
                except requests.ConnectionError:
                    time.sleep(3)
            else:
                pytest.fail(f"Service '{service_name}' did not become healthy within {timeout} seconds.")

        print("\n--- All API services are healthy, proceeding with tests ---")
        yield
    
    finally:
        print("\n--- Tearing down Docker services ---")
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "down", "-v", "--remove-orphans"],
            check=False, capture_output=True
        )


@pytest.fixture(scope="session")
def api_endpoints(docker_services):
    """
    Provides the hardcoded URLs for the services, dependent on the docker_services fixture.
    """
    return {
        "ingestion": "http://localhost:8000",
        "query": "http://localhost:8001"
    }


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """
    Provides a SQLAlchemy Engine, ensuring the Docker services are running first.
    """
    db_url = os.getenv("HOST_DATABASE_URL", "postgresql://user:password@localhost:5432/portfolio_db")
    
    # Wait for the database to be connectable
    engine = create_engine(db_url)
    timeout = 60
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("--- Database is connectable ---")
            yield engine
            engine.dispose()
            return
        except exc.OperationalError:
            time.sleep(2)
    
    pytest.fail(f"Database did not become connectable within {timeout} seconds.")


# List of all tables to be cleaned. Centralized here.
TABLES_TO_TRUNCATE = [
    "position_state",
    "business_dates",
    "portfolio_valuation_jobs", "portfolio_aggregation_jobs", "transaction_costs", "cashflows", "position_history", "daily_position_snapshots",
    "position_timeseries", "portfolio_timeseries", "transactions", "market_prices",
    "instruments", "fx_rates", "portfolios", "processed_events", "outbox_events"
]

@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    A function-scoped fixture that cleans all data from tables using TRUNCATE.
    """
    print("\n--- Cleaning database tables (function scope) ---")
    truncate_query = text(f"TRUNCATE TABLE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE;")
    with db_engine.begin() as connection:
        connection.execute(truncate_query)
    yield

@pytest_asyncio.fixture(scope="function")
async def async_db_session(db_engine):
    """
    A function-scoped async fixture that provides a SQLAlchemy AsyncSession.
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

@pytest.fixture(scope="module")
def poll_for_data():
    """
    Provides a generic polling utility to query an endpoint until a condition is met.
    """
    def _poll(url: str, validation_func, timeout: int = 45, fail_message: str = "Polling timed out"):
        start_time = time.time()
        last_response_data = None
        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    last_response_data = response.json()
                    if validation_func(last_response_data):
                        return last_response_data
            except requests.ConnectionError:
                pass 
            time.sleep(1)
        
        pytest.fail(
            f"{fail_message} after {timeout} seconds for URL {url}. "
            f"Last response: {last_response_data}"
        )
    return _poll

@pytest.fixture(scope="module")
def poll_db_until(db_engine):
    """
    Provides a generic polling utility to query the database until a condition is met.
    """
    def _poll(
        query: str,
        validation_func: Callable[[Any], bool],
        params: dict = {},
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "DB Polling timed out."
    ):
        start_time = time.time()
        last_result = None
        while time.time() - start_time < timeout:
            with Session(db_engine) as session:
                result = session.execute(text(query), params).fetchone()
                last_result = result
                if validation_func(result):
                    return
            time.sleep(interval)
        
        pytest.fail(
            f"{fail_message} after {timeout} seconds. Last result: {last_result}"
        )
    return _poll