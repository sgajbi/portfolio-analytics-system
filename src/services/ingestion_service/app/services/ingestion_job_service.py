from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from app.DTOs.ingestion_job_dto import IngestionJobResponse, IngestionJobStatus


@dataclass
class _IngestionJobRecord:
    job_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    correlation_id: str
    request_id: str
    trace_id: str
    submitted_at: datetime
    status: IngestionJobStatus = "accepted"
    completed_at: datetime | None = None
    failure_reason: str | None = None

    def to_response(self) -> IngestionJobResponse:
        return IngestionJobResponse(
            job_id=self.job_id,
            endpoint=self.endpoint,
            entity_type=self.entity_type,
            status=self.status,
            accepted_count=self.accepted_count,
            idempotency_key=self.idempotency_key,
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            trace_id=self.trace_id,
            submitted_at=self.submitted_at,
            completed_at=self.completed_at,
            failure_reason=self.failure_reason,
        )


class IngestionJobService:
    """
    Tracks ingestion request lifecycle for API-first operational visibility.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, _IngestionJobRecord] = {}
        self._lock = RLock()

    def create_job(
        self,
        *,
        job_id: str,
        endpoint: str,
        entity_type: str,
        accepted_count: int,
        idempotency_key: str | None,
        correlation_id: str,
        request_id: str,
        trace_id: str,
    ) -> None:
        with self._lock:
            self._jobs[job_id] = _IngestionJobRecord(
                job_id=job_id,
                endpoint=endpoint,
                entity_type=entity_type,
                accepted_count=accepted_count,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
                submitted_at=datetime.now(UTC),
            )

    def mark_queued(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            job.status = "queued"
            job.completed_at = datetime.now(UTC)
            job.failure_reason = None

    def mark_failed(self, job_id: str, failure_reason: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.failure_reason = failure_reason

    def get_job(self, job_id: str) -> IngestionJobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_response() if job else None

    def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[IngestionJobResponse]:
        with self._lock:
            values = list(self._jobs.values())

        filtered = [
            job
            for job in values
            if (status is None or job.status == status)
            and (entity_type is None or job.entity_type == entity_type)
        ]
        filtered.sort(key=lambda job: job.submitted_at, reverse=True)
        return [job.to_response() for job in filtered[:limit]]


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
