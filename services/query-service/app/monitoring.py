# services/query-service/app/monitoring.py
from prometheus_client import Histogram

# Define a histogram to measure the duration of database operations.
# We include 'repository' and 'method' labels to pinpoint slow queries.
DB_OPERATION_LATENCY_SECONDS = Histogram(
    "db_operation_latency_seconds",
    "Latency of database operations in seconds.",
    ["repository", "method"]
)

# A dictionary to hold all custom metrics for easy injection and access.
CUSTOM_METRICS = {
    "db_latency": DB_OPERATION_LATENCY_SECONDS
}