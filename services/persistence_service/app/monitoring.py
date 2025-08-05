# services/persistence_service/app/monitoring.py
from prometheus_fastapi_instrumentator import Instrumentator

def setup_metrics(app):
    """
    Sets up and attaches the Prometheus FastAPI Instrumentator to the app.
    This automatically creates a /metrics endpoint and instruments all
    API endpoints with default metrics (latency, requests, etc.).
    """
    instrumentator = Instrumentator(
        should_instrument_requests=True,
        should_instrument_response_size=True,
        should_instrument_requests_latency=True,
        excluded_handlers=["/metrics"], # Avoid instrumenting the metrics endpoint itself
    )
    instrumentator.instrument(app).expose(app)