# src/libs/portfolio-common/portfolio_common/monitoring.py
import logging
from typing import Optional
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# DB metrics (used by portfolio_common.utils.async_timed, etc.)
# --------------------------------------------------------------------------------------
DB_OPERATION_LATENCY_SECONDS = Histogram(
    "db_operation_latency_seconds",
    "Latency of database operations in seconds",
    labelnames=("repository", "method"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def db_timer(operation: str):
    """
    Backwards/ergonomic helper. Times a DB operation using a generic repository label.
    Usage:
        with db_timer("transaction_upsert"):
            ...
    """
    return DB_OPERATION_LATENCY_SECONDS.labels(repository="db", method=operation).time()

# --------------------------------------------------------------------------------------
# Kafka (generic) metrics – available for any service to use
# --------------------------------------------------------------------------------------
KAFKA_MESSAGES_PUBLISHED_TOTAL = Counter(
    "kafka_messages_published_total",
    "Number of messages successfully published to Kafka",
    labelnames=("topic",),
)

KAFKA_PUBLISH_ERRORS_TOTAL = Counter(
    "kafka_publish_errors_total",
    "Number of Kafka publish errors",
    labelnames=("topic", "error"),
)

KAFKA_MESSAGES_CONSUMED_TOTAL = Counter(
    "kafka_messages_consumed_total",
    "Number of messages consumed from Kafka",
    labelnames=("topic", "group_id"),
)

KAFKA_CONSUME_ERRORS_TOTAL = Counter(
    "kafka_consume_errors_total",
    "Number of Kafka consume errors",
    labelnames=("topic", "error"),
)

KAFKA_PUBLISH_LATENCY_SECONDS = Histogram(
    "kafka_publish_latency_seconds",
    "Kafka publish latency in seconds by topic",
    labelnames=("topic",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def observe_kafka_published(topic: str, count: int = 1) -> None:
    KAFKA_MESSAGES_PUBLISHED_TOTAL.labels(topic).inc(count)

def observe_kafka_publish_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_PUBLISH_ERRORS_TOTAL.labels(topic, error).inc(count)

def observe_kafka_consumed(topic: str, group_id: str, count: int = 1) -> None:
    KAFKA_MESSAGES_CONSUMED_TOTAL.labels(topic, group_id).inc(count)

def observe_kafka_consume_error(topic: str, error: str, count: int = 1) -> None:
    KAFKA_CONSUME_ERRORS_TOTAL.labels(topic, error).inc(count)

def kafka_publish_timer(topic: str):
    """Context manager that observes Kafka publish latency for a topic."""
    return KAFKA_PUBLISH_LATENCY_SECONDS.labels(topic).time()

# --------------------------------------------------------------------------------------
# Outbox Dispatcher Metrics
# --------------------------------------------------------------------------------------
_OUTBOX_PUBLISHED = Counter(
    "outbox_events_published_total",
    "Number of outbox events successfully published to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_FAILED = Counter(
    "outbox_events_failed_total",
    "Number of outbox events that failed to publish to Kafka",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_RETRIED = Counter(
    "outbox_events_retried_total",
    "Number of outbox events marked for retry after failed publishes",
    labelnames=("aggregate_type", "topic"),
)

_OUTBOX_PENDING = Gauge(
    "outbox_events_pending",
    "Total number of PENDING outbox events in the database",
)

_OUTBOX_BATCH_SECONDS = Histogram(
    "outbox_dispatch_batch_seconds",
    "Time taken to process one outbox dispatch batch (lock, publish, update statuses).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

def observe_outbox_published(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_PUBLISHED.labels(aggregate_type, topic).inc(count)

def observe_outbox_failed(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_FAILED.labels(aggregate_type, topic).inc(count)

def observe_outbox_retried(aggregate_type: str, topic: str, count: int = 1) -> None:
    _OUTBOX_RETRIED.labels(aggregate_type, topic).inc(count)

def set_outbox_pending(total_pending: int) -> None:
    _OUTBOX_PENDING.set(total_pending)

def outbox_batch_timer():
    """Context manager that observes outbox batch duration."""
    return _OUTBOX_BATCH_SECONDS.time()

# --------------------------------------------------------------------------------------
# Reprocessing & Epoch Metrics
# --------------------------------------------------------------------------------------
INSTRUMENT_REPROCESSING_TRIGGERS_PENDING = Gauge(
    "instrument_reprocessing_triggers_pending",
    "Total number of pending instrument reprocessing triggers awaiting fan-out."
)

EPOCH_MISMATCH_DROPPED_TOTAL = Counter(
    "epoch_mismatch_dropped_total",
    "Number of Kafka messages dropped due to a stale epoch.",
    labelnames=("service_name", "topic", "portfolio_id", "security_id"),
)

REPROCESSING_ACTIVE_KEYS_TOTAL = Gauge(
    "reprocessing_active_keys_total",
    "Total number of (portfolio, security) keys currently in a REPROCESSING state."
)

SNAPSHOT_LAG_SECONDS = Histogram(
    "snapshot_lag_seconds",
    "The lag between the latest business date and a key's watermark, in seconds.",
    buckets=(3600, 86400, 172800, 604800, 2592000) # 1hr, 1d, 2d, 1wk, 30d
)

SCHEDULER_GAP_DAYS = Histogram(
    "scheduler_gap_days",
    "The gap in days between the latest business date and a key's watermark.",
    buckets=(1, 2, 5, 10, 30, 90, 365)
)

# --- Valuation Pipeline Metrics ---
VALUATION_JOBS_CREATED_TOTAL = Counter(
    "valuation_jobs_created_total",
    "Total number of valuation jobs created by the scheduler.",
    labelnames=("portfolio_id", "security_id"),
)

VALUATION_JOBS_SKIPPED_TOTAL = Counter(
    "valuation_jobs_skipped_total",
    "Total number of valuation jobs skipped by the consumer due to no position history.",
    labelnames=("portfolio_id", "security_id"),
)

VALUATION_JOBS_FAILED_TOTAL = Counter(
    "valuation_jobs_failed_total",
    "Total number of valuation jobs that failed for terminal reasons (e.g., missing ref data).",
    labelnames=("portfolio_id", "security_id", "reason"),
)

# --- NEW METRIC (RFC 022) ---
CASHFLOWS_CREATED_TOTAL = Counter(
    "cashflows_created_total",
    "Total number of cashflows created, by classification and timing.",
    ["classification", "timing"]
)
# --- END NEW METRIC ---

# --------------------------------------------------------------------------------------
# Optional generic HTTP metrics (use across services if helpful)
# --------------------------------------------------------------------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP requests total",
    labelnames=("service", "method", "path", "status"),
)

HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    labelnames=("service", "method", "path"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

def http_request_timer(service: str, method: str, path: str):
    """Context manager for timing an HTTP request handler."""
    return HTTP_REQUEST_LATENCY_SECONDS.labels(service, method, path).time()

UNCLASSIFIED_ALLOCATION_MARKET_VALUE = Gauge(
    "unclassified_allocation_market_value_total",
    "Total market value of positions in the 'Unclassified' allocation bucket.",
    ["portfolio_id", "dimension"]
)

# --- NEW METRIC FOR REVIEW API ---
REVIEW_GENERATION_DURATION_SECONDS = Histogram(
    "review_generation_duration_seconds",
    "Time taken to generate a full portfolio review report.",
    labelnames=("portfolio_id",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# --- NEW METRICS FOR POSITION ANALYTICS API (RFC 017) ---
POSITION_ANALYTICS_DURATION_SECONDS = Histogram(
    "position_analytics_duration_seconds",
    "Time taken to generate a position-level analytics report.",
    labelnames=("portfolio_id",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0),
)

POSITION_ANALYTICS_SECTION_REQUESTED_TOTAL = Counter(
    "position_analytics_section_requested_total",
    "Total number of times each section has been requested in the Position Analytics API.",
    labelnames=("section_name",),
)

CONCENTRATION_CALCULATION_DURATION_SECONDS = Histogram(
    "concentration_calculation_duration_seconds",
    "Time taken to generate a full portfolio concentration report.",
    labelnames=("portfolio_id",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

CONCENTRATION_LOOKTHROUGH_REQUESTS_TOTAL = Counter(
    "concentration_lookthrough_requests_total",
    "Total number of concentration requests where fund look-through was enabled.",
    labelnames=("portfolio_id",),
)
 