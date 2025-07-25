import pytest
import requests
import time
from testcontainers.compose import DockerCompose

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
        
        # Poll the health check endpoint until it's ready
        start_time = time.time()
        timeout = 120  # 2 minutes timeout
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url)
                if response.status_code == 200:
                    print(f"Ingestion service is healthy at {health_url}")
                    break
            except requests.ConnectionError:
                time.sleep(1) # Service is not up yet, wait and retry
        else:
            pytest.fail(f"Ingestion service did not become healthy within {timeout} seconds.")
            
        yield compose

def test_services_are_running(docker_services: DockerCompose):
    """
    A simple test to confirm that the Docker Compose fixture is working
    and the services have started successfully.
    """
    assert True