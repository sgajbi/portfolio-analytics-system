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

# List of all tables to be cleaned. Centralized here.
TABLES_TO_TRUNCATE = [
    "business_dates", # <-- ADDED
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

@pytest.fixture(scope="module")
def clean_db_module(db_engine):
    """
    A module-scoped fixture that safely cleans the database between test modules.
    It stops all services that might hold DB locks, truncates the tables,
    and then restarts the services to ensure a clean state.
    """
    services_to_manage = [
        "persistence_service",
        "cost_calculator_service",
        "cashflow_calculator_service",
        "position_calculator_service",
        "position_valuation_calculator",
        "timeseries_generator_service",
    ]

    print("\n--- Stopping services for module cleanup ---")
    subprocess.run(["docker", "compose", "stop"] + services_to_manage, check=True, capture_output=True, text=True)

    print("\n--- Cleaning database tables (module scope) ---")
    truncate_query = text(f"TRUNCATE TABLE {', '.join(TABLES_TO_TRUNCATE)} RESTART IDENTITY CASCADE;")
    with db_engine.begin() as connection:
        connection.execute(truncate_query)
    
    print("\n--- Restarting services after module cleanup ---")
    subprocess.run(["docker", "compose", "start"] + services_to_manage, check=True, capture_output=True, text=True)

    # It's critical to wait for services to be healthy again before tests proceed.
    print("\n--- Waiting for services to restart... ---")
    time.sleep(15)

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

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

@pytest.fixture(scope="module")
def poll_for_data():
    """
    Provides a generic polling utility to query an endpoint until a condition is met.
    
    Args:
        url (str): The API endpoint to poll.
        validation_func (callable): A function that takes the response JSON and returns True if valid.
        timeout (int): The maximum time to wait in seconds.
    Returns:
        A callable polling function.
    """
    def _poll(url: str, validation_func, timeout: int = 45):
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
                # Service may not be ready, just continue polling
                pass 
            time.sleep(1)
        
        pytest.fail(
            f"Polling timed out after {timeout} seconds for URL {url}. "
            f"Last response: {last_response_data}"
        )
    return _poll