from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

IngestionJobStatus = Literal["accepted", "queued", "failed"]


class IngestionJobResponse(BaseModel):
    job_id: str = Field(
        description="Asynchronous ingestion job identifier.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    endpoint: str = Field(
        description="Ingestion API endpoint that created this job.",
        examples=["/ingest/transactions"],
    )
    entity_type: str = Field(
        description="Canonical entity type accepted by the endpoint.",
        examples=["transaction"],
    )
    status: IngestionJobStatus = Field(
        description="Current ingestion job lifecycle state.",
        examples=["queued"],
    )
    accepted_count: int = Field(
        ge=0,
        description="Number of records accepted by the ingestion request.",
        examples=[125],
    )
    idempotency_key: str | None = Field(
        default=None,
        description="Client idempotency key if supplied for the request.",
        examples=["ingestion-transactions-batch-20260228-001"],
    )
    correlation_id: str = Field(
        description="Correlation identifier for cross-service traceability.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    request_id: str = Field(
        description="Request identifier for ingress request tracking.",
        examples=["REQ:3a63936e-bf29-41e2-9f16-faf4e561d845"],
    )
    trace_id: str = Field(
        description="Distributed trace identifier for observability stitching.",
        examples=["4bf92f3577b34da6a3ce929d0e0e4736"],
    )
    submitted_at: datetime = Field(
        description="Timestamp when the ingestion job was accepted.",
        examples=["2026-02-28T13:22:24.201Z"],
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when the job reached a terminal or queued state.",
        examples=["2026-02-28T13:22:24.994Z"],
    )
    failure_reason: str | None = Field(
        default=None,
        description="Failure reason when status is failed.",
        examples=["Kafka publish timeout for topic raw_transactions."],
    )
    retry_count: int = Field(
        ge=0,
        description="Number of retry attempts executed for this ingestion job.",
        examples=[1],
    )
    last_retried_at: datetime | None = Field(
        default=None,
        description="Timestamp of the most recent retry attempt.",
        examples=["2026-02-28T13:24:10.512Z"],
    )


class IngestionJobListResponse(BaseModel):
    jobs: list[IngestionJobResponse] = Field(
        description="Ingestion jobs matching the requested filters."
    )
    total: int = Field(
        ge=0,
        description="Number of jobs returned in this response.",
        examples=[20],
    )
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Opaque cursor to fetch the next page of jobs, based on descending ingestion job order."
        ),
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )


class IngestionJobFailureResponse(BaseModel):
    failure_id: str = Field(
        description="Unique failure record identifier for this job failure event.",
        examples=["fail_01J5S27P16BSKQ3R2P2HK67GQZ"],
    )
    job_id: str = Field(
        description="Ingestion job identifier this failure event belongs to.",
        examples=["job_01J5S0J6D3BAVMK2E1V0WQ7MCC"],
    )
    failure_phase: str = Field(
        description="Pipeline phase where the job failure occurred.",
        examples=["publish"],
    )
    failure_reason: str = Field(
        description="Detailed failure reason captured at runtime.",
        examples=["Kafka publish timeout for topic raw_transactions."],
    )
    failed_record_keys: list[str] = Field(
        default_factory=list,
        description="Subset of record keys that failed during publish/retry processing.",
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    failed_at: datetime = Field(
        description="Timestamp when this failure event was captured.",
        examples=["2026-02-28T13:23:09.021Z"],
    )


class IngestionJobFailureListResponse(BaseModel):
    failures: list[IngestionJobFailureResponse] = Field(
        description="Failure events captured for the requested ingestion job."
    )
    total: int = Field(
        ge=0,
        description="Number of failure events returned in this response.",
        examples=[1],
    )


class IngestionHealthSummaryResponse(BaseModel):
    total_jobs: int = Field(
        ge=0,
        description="Total ingestion jobs stored in operational state.",
        examples=[2450],
    )
    accepted_jobs: int = Field(
        ge=0,
        description="Total jobs currently in accepted state.",
        examples=[3],
    )
    queued_jobs: int = Field(
        ge=0,
        description="Total jobs currently queued for asynchronous processing.",
        examples=[7],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Total jobs currently marked as failed.",
        examples=[2],
    )
    backlog_jobs: int = Field(
        ge=0,
        description="Operational backlog count (accepted + queued).",
        examples=[10],
    )


class IngestionSloStatusResponse(BaseModel):
    lookback_minutes: int = Field(
        ge=1,
        description="Lookback window in minutes used for SLO calculations.",
        examples=[60],
    )
    total_jobs: int = Field(
        ge=0,
        description="Number of jobs observed in the lookback window.",
        examples=[320],
    )
    failed_jobs: int = Field(
        ge=0,
        description="Number of failed jobs observed in the lookback window.",
        examples=[4],
    )
    failure_rate: Decimal = Field(
        ge=Decimal("0"),
        description="Failed jobs divided by total jobs in the lookback window.",
        examples=["0.0125"],
    )
    p95_queue_latency_seconds: float = Field(
        ge=0.0,
        description="95th percentile latency from job submission to queue completion.",
        examples=[1.42],
    )
    backlog_age_seconds: float = Field(
        ge=0.0,
        description="Age in seconds of the oldest non-terminal ingestion job.",
        examples=[74.0],
    )
    breach_failure_rate: bool = Field(
        description="Whether failure rate exceeds configured threshold.",
        examples=[False],
    )
    breach_queue_latency: bool = Field(
        description="Whether p95 queue latency exceeds configured threshold.",
        examples=[False],
    )
    breach_backlog_age: bool = Field(
        description="Whether backlog age exceeds configured threshold.",
        examples=[False],
    )


class IngestionRetryRequest(BaseModel):
    record_keys: list[str] = Field(
        default_factory=list,
        description=(
            "Optional subset of record keys to replay. Empty list replays full stored payload."
        ),
        examples=[["TXN-2026-000145", "TXN-2026-000146"]],
    )
    dry_run: bool = Field(
        default=False,
        description="When true, validates retry scope without publishing messages.",
        examples=[False],
    )


class IngestionOpsModeResponse(BaseModel):
    mode: Literal["normal", "paused", "drain"] = Field(
        description="Current ingestion operations mode.",
        examples=["normal"],
    )
    replay_window_start: datetime | None = Field(
        default=None,
        description="Start timestamp for allowed retry replay operations.",
        examples=["2026-03-01T00:00:00Z"],
    )
    replay_window_end: datetime | None = Field(
        default=None,
        description="End timestamp for allowed retry replay operations.",
        examples=["2026-03-01T06:00:00Z"],
    )
    updated_by: str | None = Field(
        default=None,
        description="Principal or automation actor who last changed ops mode.",
        examples=["ops_automation"],
    )
    updated_at: datetime = Field(
        description="Timestamp of last ops mode update.",
        examples=["2026-02-28T22:15:07.234Z"],
    )


class IngestionOpsModeUpdateRequest(BaseModel):
    mode: Literal["normal", "paused", "drain"] = Field(
        description="Target ingestion operations mode.",
        examples=["paused"],
    )
    replay_window_start: datetime | None = Field(
        default=None,
        description="Optional replay window start for retry operations.",
        examples=["2026-03-01T00:00:00Z"],
    )
    replay_window_end: datetime | None = Field(
        default=None,
        description="Optional replay window end for retry operations.",
        examples=["2026-03-01T06:00:00Z"],
    )
    updated_by: str | None = Field(
        default=None,
        description="Actor label for audit trail.",
        examples=["ops_automation"],
    )


class ConsumerDlqEventResponse(BaseModel):
    event_id: str = Field(
        description="Unique audit identifier for a consumer dead-letter event.",
        examples=["cdlq_01J5VK4Y4EPMTVF1B0HF4CAHB6"],
    )
    original_topic: str = Field(
        description="Original Kafka topic where message processing failed.",
        examples=["raw_transactions"],
    )
    consumer_group: str = Field(
        description="Consumer group that rejected the message.",
        examples=["persistence-service-group"],
    )
    dlq_topic: str = Field(
        description="Dead-letter topic where failed message was published.",
        examples=["persistence_service.dlq"],
    )
    original_key: str | None = Field(
        default=None,
        description="Original message key, if available.",
        examples=["TXN-2026-000145"],
    )
    error_reason: str = Field(
        description="Error reason captured when consumer rejected the message.",
        examples=["ValidationError: portfolio_id is required"],
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier associated with the failed message.",
        examples=["ING:7f4a64b0-35f4-41bc-8f74-cb556f2ad9a3"],
    )
    payload_excerpt: str | None = Field(
        default=None,
        description="Truncated payload excerpt for operational triage.",
        examples=['{"transaction_id":"TXN-2026-000145"}'],
    )
    observed_at: datetime = Field(
        description="Timestamp when the DLQ event was observed.",
        examples=["2026-02-28T22:11:05.812Z"],
    )


class ConsumerDlqEventListResponse(BaseModel):
    events: list[ConsumerDlqEventResponse] = Field(
        description="Consumer dead-letter events for operational triage."
    )
    total: int = Field(
        ge=0,
        description="Number of DLQ events returned.",
        examples=[25],
    )
