# tests/e2e/conftest.py
import pytest
import requests
import time

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