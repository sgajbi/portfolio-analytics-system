import pytest
import requests
import time
import psycopg2
from testcontainers.compose import DockerCompose
from decimal import Decimal

@pytest.fixture(scope="session")
def docker_services(request):
    """
    A session-scoped fixture that starts the Docker Compose stack and waits for the
    ingestion-service to become healthy before yielding to the tests.
    """
    compose = DockerCompose(".", compose_file_name="docker-compose.yml")
    with compose:
        host = compose.get_service_host("ingestion-service", 8000)
        port = compose.get_service_port("ingestion-service", 8000)
        health_url = f"http://{host}:{port}/health"
        
        start_time = time.time()
        timeout = 180
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url)
                if response.status_code == 200:
                    print(f"Ingestion service is healthy at {health_url}")
                    break
            except requests.ConnectionError:
                time.sleep(2)
        else:
            pytest.fail(f"Ingestion service did not become healthy within {timeout} seconds.")
            
        yield compose

@pytest.fixture(scope="module")
def db_connection(docker_services: DockerCompose):
    """
    A module-scoped fixture to provide a clean database connection for each test module.
    """
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    url = f"postgresql://user:password@{host}:{port}/portfolio_db"
    conn = psycopg2.connect(url)
    yield conn
    conn.close()

@pytest.fixture(scope="function")
def clean_db(db_connection):
    """
    A function-scoped fixture that cleans all relevant tables before each test.
    This ensures test idempotency.
    """
    with db_connection.cursor() as cursor:
        cursor.execute("""
            TRUNCATE TABLE daily_position_snapshots, position_history, 
                         cashflows, transaction_costs, transactions, instruments, 
                         market_prices, fx_rates, portfolios, portfolio_timeseries, position_timeseries
            RESTART IDENTITY;
        """)
    db_connection.commit()
    yield