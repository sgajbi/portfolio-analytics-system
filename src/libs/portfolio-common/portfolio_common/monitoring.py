# libs/portfolio-common/portfolio_common/monitoring.py
from prometheus_client import Histogram, Counter

# Define a histogram to measure the duration of database operations.
# We include 'repository' and 'method' labels to pinpoint slow queries.
DB_OPERATION_LATENCY_SECONDS = Histogram(
    "db_operation_latency_seconds",
    "Latency of database operations in seconds.",
    ["repository", "method"]
)

# --- NEW METRIC ---
# Define a counter for messages published to Kafka.
# The 'topic' label allows us to see the message volume for each topic.
KAFKA_MESSAGES_PUBLISHED_TOTAL = Counter(
    "kafka_messages_published_total",
    "Total number of messages published to Kafka.",
    ["topic"]
)


# A dictionary to hold all custom metrics for easy injection and access.
CUSTOM_METRICS = {
    "db_latency": DB_OPERATION_LATENCY_SECONDS,
    "kafka_published": KAFKA_MESSAGES_PUBLISHED_TOTAL
}