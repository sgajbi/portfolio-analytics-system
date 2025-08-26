# tests/conftest.py
import pytest
import requests
import time
import subprocess
import os
import sys
from testcontainers.compose import DockerCompose
# UPDATED IMPORTS
from sqlalchemy import create_engine, text
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from typing import Callable, Any


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def docker_services(request):
    """
    A session-scoped fixture that starts the Docker Compose stack and waits for the
    ingestion_service and query_service to become healthy before yielding to the tests.

    This fixture now uses a manual polling mechanism in Python instead of relying on
    Docker's '--wait' flag to provide more resilient and reliable startup for tests.
    """
    compose = DockerCompose(".", compose_file_name="docker-compose.yml")
    
    try:
        # Manually call up() without --wait to avoid the brittle healthcheck enforcement at startup
        compose.up()

        print("\n--- Waiting for API services to become healthy ---")
        services_to_check = {
            "ingestion_service": 8000,
            "query_service": 8001
        }
        timeout = 180
        
        for service_name, port in services_to_check.items():
            host = compose.get_service_host(service_name, port)
            service_port = compose.get_service_port(service_name, port)
            health_url = f"http://{host}:{service_port}/health/ready"
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = requests.get(health_url, timeout=2)
                    if response.status_code == 200:
                        print(f"--- Service '{service_name}' is healthy at {health_url} ---")
                        break
                except requests.ConnectionError:
                    time.sleep(2)
            else:
                pytest.fail(f"Service '{service_name}' did not become healthy within {timeout} seconds.")
            
        print("\n--- All API services are healthy, proceeding with tests ---")
        yield compose
    finally:
        # Ensure services are torn down at the end of the session
        compose.down()

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

# List of all tables to be cleaned. Centralized here.
TABLES_TO_TRUNCATE = [
    "position_state", # NEW: Add new table to be cleaned
    "business_dates",
    "portfolio_valuation_jobs", "portfolio_aggregation_jobs", "transaction_costs", "cashflows", "position_history", "daily_position_snapshots",
    "position_timeseries", "portfolio_timeseries", "transactions", "market_prices",
    "instruments", "fx_rates", "portfolios", "processed_events", "outbox_events"
]

@pytest.fixture(scope="function")
def clean_db(db_engine):
    """
    A function-scoped fixture that cleans all data from tables using TRUNCATE.
    Used for integration and unit tests that require a clean state for each test function.
    """
    print("\n--- Cleaning database tables (function scope) ---")
    truncate_query = text(f"TRUNCATE TABLE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE;")
    with db_engine.begin() as connection:
        connection.execute(truncate_query)
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

# --- E2E Helper Fixtures (Moved from tests/e2e/conftest.py) ---

@pytest.fixture(scope="module")
def api_endpoints(docker_services):
    """
    Provides the URLs for the ingestion and query services for the entire test module.
    """
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    query_host = docker_services.get_service_host("query_service", 8001)
    query_port = docker_services.get_service_port("query_service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

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