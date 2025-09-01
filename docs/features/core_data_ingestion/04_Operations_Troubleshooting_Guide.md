# Operations & Troubleshooting Guide: Ingestion Service

This guide provides operational instructions for monitoring and troubleshooting the `ingestion_service`.

## 1. Observability & Monitoring

The service is instrumented with Prometheus and provides metrics at the `/metrics` endpoint. A pre-built Grafana dashboard is available for visualization.

### Key Metrics to Watch

* **API Request Rate & Latency (`http_requests_total`, `http_request_latency_seconds`):**
    * **What it is:** Standard RED (Rate, Errors, Duration) metrics for all HTTP endpoints.
    * **What to watch for:** Sudden spikes in the error rate (non-2xx status codes) or a significant increase in latency can indicate a problem with the service or its dependencies (like Kafka).
* **Kafka Messages Published (`kafka_messages_published_total`):**
    * **What it is:** A counter for every message successfully handed off to the Kafka producer buffer.
    * **What to watch for:** This count should correlate directly with the incoming API request volume. If the API request rate is high but this metric is flat, it indicates the producer is failing to publish messages.
* **Service Health (`/health/ready`):**
    * **What it is:** A readiness probe that actively checks the connection to Kafka.
    * **What to watch for:** If this endpoint returns a `503 Service Unavailable`, the service cannot connect to the Kafka brokers. This is a critical alert condition.

## 2. Structured Logging & Tracing

All logs from the `ingestion_service` are structured JSON, which is ideal for log aggregation systems like Splunk or ELK. Every log entry is enriched with the `correlation_id` for the request.

**To trace a request:**
1.  Find the `correlation_id` for the failed request. This can be obtained from the `X-Correlation-ID` response header or by searching the logs for a known detail (e.g., a `transaction_id`).
2.  Use this `correlation_id` to filter logs across all downstream services to see the entire lifecycle of the ingested data.

## 3. Common Failure Scenarios & Resolutions

| Scenario | Symptom(s) in API / Logs | Key Log Message(s) / Metric Alert | Resolution / Action |
| :--- | :--- | :--- | :--- |
| **Kafka is Unavailable** | `503 Service Unavailable` on `/health/ready`. `500 Internal Server Error` on ingest endpoints. | `FATAL: Could not initialize Kafka producer` in service logs. | **Escalate to Ops.** The Kafka cluster is down or unreachable. Check the health of the `kafka` and `zookeeper` containers. |
| **Malformed Client Payload** | `422 Unprocessable Entity` API response. | `pydantic.ValidationError` in service logs. | **Inform the client team.** The request body does not match the API schema. Provide them with the validation error from the logs. |
| **Producer Failing to Publish** | `202 Accepted` responses, but no data appears downstream. | `Message delivery failed...` errors in service logs. `kafka_publish_errors_total` metric is increasing. | **Investigate Kafka health.** The cluster may be degraded (e.g., disk full, leader election issues). |