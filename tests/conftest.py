# tests/conftest.py
import pytest
import requests
import time
import psycopg2
import subprocess
import os
from testcontainers.compose import DockerCompose
import sys


# --- UPDATED PATH LOGIC ---
# __file__ is now in tests/, so we just need to go up one level to get the project root.
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
        # Before starting tests, ensure the DB is fully migrated
        print("\n--- Ensuring initial migration is complete ---")
        migration_runner = compose.get_container("migration-runner")
        # Ensure migration-runner output is captured for debugging
        exit_code = migration_runner.wait()
        if exit_code != 0:
            logs = migration_runner.get_logs()
            pytest.fail(f"Migration runner failed to start. Exit code: {exit_code}\nLogs:\n{logs}")
        print("--- Initial migration complete ---")

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
    A module-scoped fixture to provide a database connection for each test module.
    """
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    # Corrected DB URL to use host and port dynamically
    url = f"postgresql://{os.getenv('POSTGRES_USER', 'user')}:{os.getenv('POSTGRES_PASSWORD', 'password')}@{host}:{port}/{os.getenv('POSTGRES_DB', 'portfolio_db')}"
    conn = psycopg2.connect(url)
    conn.autocommit = True
    yield conn
    conn.close()

@pytest.fixture(scope="function")
def clean_db(docker_services):
    """
    A function-scoped fixture that completely resets the database schema
    using Alembic before each test. This is the most robust way to ensure
    test idempotency.
    """
    print("\n--- Resetting database schema with Alembic ---")
    
    # Alembic's env.py is configured to use HOST_DATABASE_URL for local runs
    # We must provide it to the subprocess environment
    env = os.environ.copy()
    host = docker_services.get_service_host("postgres", 5432)
    port = docker_services.get_service_port("postgres", 5432)
    # Ensure correct environment variables are passed, reading from .env if possible
    # Fallback to defaults from config if .env not loaded (though testcontainers load it)
    db_user = os.getenv("POSTGRES_USER", "user")
    db_password = os.getenv("POSTGRES_PASSWORD", "password")
    db_name = os.getenv("POSTGRES_DB", "portfolio_db")
    env["HOST_DATABASE_URL"] = f"postgresql://{db_user}:{db_password}@{host}:{port}/{db_name}"

    # Downgrade to an empty schema
    downgrade_result = subprocess.run(
        ["alembic", "downgrade", "base"],
        capture_output=True, 
        text=True, env=env, shell=True # shell=True for Windows Git Bash compatibility
    )
    if downgrade_result.returncode != 0:
        pytest.fail(f"Alembic downgrade failed:\nSTDOUT:\n{downgrade_result.stdout}\nSTDERR:\n{downgrade_result.stderr}")

    # Upgrade to the latest schema
    upgrade_result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env, shell=True # shell=True for Windows Git Bash compatibility
    )
    if upgrade_result.returncode != 0:
        pytest.fail(f"Alembic upgrade failed:\nSTDOUT:\n{upgrade_result.stdout}\nSTDERR:\n{upgrade_result.stderr}")

    print("--- Database reset complete ---")
    yield