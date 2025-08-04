# tests/conftest.py
import pytest
import requests
import time
import psycopg2
import subprocess
import os
from testcontainers.compose import DockerCompose
import sys
# UPDATED IMPORTS
from sqlalchemy import create_engine, MetaData


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(scope="session")
def docker_services(request):
    """
    A session-scoped fixture that starts the Docker Compose stack and waits for the
    ingestion-service to become healthy before yielding to the tests.
    """
    compose = DockerCompose(".", compose_file_name="docker-compose.yml")
    with compose:
        print("\n--- Waiting for services to become healthy ---")

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

@pytest.fixture(scope="function")
def db_engine(docker_services: DockerCompose):
    """
    A function-scoped fixture that provides a SQLAlchemy Engine.
    This ensures every test function gets a fresh connection pool,
    guaranteeing test isolation.
    """
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    url = f"postgresql://{os.getenv('POSTGRES_USER', 'user')}:{os.getenv('POSTGRES_PASSWORD', 'password')}@{host}:{port}/{os.getenv('POSTGRES_DB', 'portfolio_db')}"
    engine = create_engine(url)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def clean_db(docker_services):
    """
    A function-scoped fixture that completely resets the database
    by dropping all tables and re-applying migrations before each test.
    """
    print("\n--- Resetting database schema ---")
    
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    db_user = os.getenv("POSTGRES_USER", "user")
    db_password = os.getenv("POSTGRES_PASSWORD", "password")
    db_name = os.getenv("POSTGRES_DB", "portfolio_db")
    db_url = f"postgresql://{db_user}:{db_password}@{host}:{port}/{db_name}"

    # Connect and drop all tables to ensure a clean slate
    engine = create_engine(db_url)
    meta = MetaData()
    with engine.connect() as connection:
        meta.reflect(bind=connection)
        meta.drop_all(bind=connection)
    engine.dispose()
    print("--- All tables dropped ---")

    # Set environment variable for the alembic command
    env = os.environ.copy()
    env["HOST_DATABASE_URL"] = db_url

    # Apply all migrations from scratch
    upgrade_result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env, shell=True
    )
    if upgrade_result.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\nSTDOUT:\n{upgrade_result.stdout}\nSTDERR:\n{upgrade_result.stderr}")

    print("--- Database reset complete ---")
    yield