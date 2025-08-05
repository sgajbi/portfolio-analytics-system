# services/persistence_service/app/monitoring.py
from prometheus_fastapi_instrumentator import Instrumentator

def setup_metrics(app):
    """
    Sets up and attaches the Prometheus FastAPI Instrumentator to the app.
    This automatically creates a /metrics endpoint and instruments all
    API endpoints with default metrics (latency, requests, etc.).
    """
    Instrumentator(
        excluded_handlers=["/metrics"]
    ).instrument(app).expose(app)