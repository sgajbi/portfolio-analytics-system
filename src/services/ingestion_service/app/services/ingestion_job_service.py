from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventResponse,
    IngestionHealthSummaryResponse,
    IngestionJobFailureResponse,
    IngestionJobResponse,
    IngestionJobStatus,
    IngestionOpsModeResponse,
    IngestionSloStatusResponse,
)
from portfolio_common.database_models import ConsumerDlqEvent as DBConsumerDlqEvent
from portfolio_common.database_models import IngestionJob as DBIngestionJob
from portfolio_common.database_models import IngestionJobFailure as DBIngestionJobFailure
from portfolio_common.database_models import IngestionOpsControl as DBIngestionOpsControl
from portfolio_common.db import get_async_db_session
from portfolio_common.monitoring import (
    INGESTION_BACKLOG_AGE_SECONDS,
    INGESTION_JOBS_CREATED_TOTAL,
    INGESTION_JOBS_FAILED_TOTAL,
    INGESTION_JOBS_RETRIED_TOTAL,
    INGESTION_MODE_STATE,
)
from sqlalchemy import and_, desc, func, select


@dataclass(slots=True)
class IngestionJobReplayContext:
    job_id: str
    endpoint: str
    entity_type: str
    accepted_count: int
    idempotency_key: str | None
    request_payload: dict[str, Any] | None
    submitted_at: datetime


@dataclass(slots=True)
class IngestionJobCreateResult:
    job: IngestionJobResponse
    created: bool


def _to_response(job: DBIngestionJob) -> IngestionJobResponse:
    return IngestionJobResponse(
        job_id=job.job_id,
        endpoint=job.endpoint,
        entity_type=job.entity_type,
        status=job.status,  # type: ignore[arg-type]
        accepted_count=job.accepted_count,
        idempotency_key=job.idempotency_key,
        correlation_id=job.correlation_id,
        request_id=job.request_id,
        trace_id=job.trace_id,
        submitted_at=job.submitted_at,
        completed_at=job.completed_at,
        failure_reason=job.failure_reason,
        retry_count=job.retry_count,
        last_retried_at=job.last_retried_at,
    )


def _to_failure_response(failure: DBIngestionJobFailure) -> IngestionJobFailureResponse:
    return IngestionJobFailureResponse(
        failure_id=failure.failure_id,
        job_id=failure.job_id,
        failure_phase=failure.failure_phase,
        failure_reason=failure.failure_reason,
        failed_record_keys=list(failure.failed_record_keys or []),
        failed_at=failure.failed_at,
    )


def _to_dlq_event_response(event: DBConsumerDlqEvent) -> ConsumerDlqEventResponse:
    return ConsumerDlqEventResponse(
        event_id=event.event_id,
        original_topic=event.original_topic,
        consumer_group=event.consumer_group,
        dlq_topic=event.dlq_topic,
        original_key=event.original_key,
        error_reason=event.error_reason,
        correlation_id=event.correlation_id,
        payload_excerpt=event.payload_excerpt,
        observed_at=event.observed_at,
    )


class IngestionJobService:
    """
    Persists ingestion lifecycle and operational controls for ingestion runbooks.
    """

    async def create_or_get_job(
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
        request_payload: dict[str, Any] | None,
    ) -> IngestionJobCreateResult:
        async for db in get_async_db_session():
            async with db.begin():
                if idempotency_key:
                    existing = await db.scalar(
                        select(DBIngestionJob)
                        .where(
                            and_(
                                DBIngestionJob.endpoint == endpoint,
                                DBIngestionJob.idempotency_key == idempotency_key,
                            )
                        )
                        .order_by(desc(DBIngestionJob.submitted_at))
                        .limit(1)
                    )
                    if existing is not None:
                        return IngestionJobCreateResult(job=_to_response(existing), created=False)

                row = DBIngestionJob(
                    job_id=job_id,
                    endpoint=endpoint,
                    entity_type=entity_type,
                    status="accepted",
                    accepted_count=accepted_count,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    request_payload=request_payload,
                )
                db.add(row)
                await db.flush()
                INGESTION_JOBS_CREATED_TOTAL.labels(
                    endpoint=endpoint, entity_type=entity_type
                ).inc()
                return IngestionJobCreateResult(job=_to_response(row), created=True)

        msg = "Unable to create ingestion job due to unavailable database session."
        raise RuntimeError(msg)

    async def mark_queued(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "queued"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = None

    async def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
        failure_phase: str = "publish",
        failed_record_keys: list[str] | None = None,
    ) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.status = "failed"
                row.completed_at = datetime.now(UTC)
                row.failure_reason = failure_reason
                db.add(
                    DBIngestionJobFailure(
                        failure_id=f"fail_{uuid4().hex}",
                        job_id=job_id,
                        failure_phase=failure_phase,
                        failure_reason=failure_reason,
                        failed_record_keys=failed_record_keys or [],
                    )
                )
                INGESTION_JOBS_FAILED_TOTAL.labels(
                    endpoint=row.endpoint,
                    entity_type=row.entity_type,
                    failure_phase=failure_phase,
                ).inc()

    async def mark_retried(self, job_id: str) -> None:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
                )
                if row is None:
                    return
                row.retry_count = int(row.retry_count or 0) + 1
                row.last_retried_at = datetime.now(UTC)
                INGESTION_JOBS_RETRIED_TOTAL.labels(
                    endpoint=row.endpoint, entity_type=row.entity_type, result="accepted"
                ).inc()

    async def get_job(self, job_id: str) -> IngestionJobResponse | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            return _to_response(row) if row else None
        return None

    async def get_job_replay_context(self, job_id: str) -> IngestionJobReplayContext | None:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionJob).where(DBIngestionJob.job_id == job_id).limit(1)
            )
            if row is None:
                return None
            payload = row.request_payload if isinstance(row.request_payload, dict) else None
            return IngestionJobReplayContext(
                job_id=row.job_id,
                endpoint=row.endpoint,
                entity_type=row.entity_type,
                accepted_count=row.accepted_count,
                idempotency_key=row.idempotency_key,
                request_payload=payload,
                submitted_at=row.submitted_at,
            )
        return None

    async def list_jobs(
        self,
        *,
        status: IngestionJobStatus | None = None,
        entity_type: str | None = None,
        submitted_from: datetime | None = None,
        submitted_to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[IngestionJobResponse], str | None]:
        async for db in get_async_db_session():
            stmt = select(DBIngestionJob)
            if status is not None:
                stmt = stmt.where(DBIngestionJob.status == status)
            if entity_type is not None:
                stmt = stmt.where(DBIngestionJob.entity_type == entity_type)
            if submitted_from is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at >= submitted_from)
            if submitted_to is not None:
                stmt = stmt.where(DBIngestionJob.submitted_at <= submitted_to)
            if cursor is not None:
                cursor_row = await db.scalar(
                    select(DBIngestionJob).where(DBIngestionJob.job_id == cursor).limit(1)
                )
                if cursor_row is not None:
                    stmt = stmt.where(DBIngestionJob.id < cursor_row.id)
            stmt = stmt.order_by(desc(DBIngestionJob.id)).limit(limit + 1)
            rows = list((await db.scalars(stmt)).all())
            has_more = len(rows) > limit
            page_rows = rows[:limit]
            next_cursor = page_rows[-1].job_id if has_more and page_rows else None
            return ([_to_response(row) for row in page_rows], next_cursor)
        return ([], None)

    async def list_failures(
        self, job_id: str, limit: int = 100
    ) -> list[IngestionJobFailureResponse]:
        async for db in get_async_db_session():
            rows = (
                await db.scalars(
                    select(DBIngestionJobFailure)
                    .where(DBIngestionJobFailure.job_id == job_id)
                    .order_by(desc(DBIngestionJobFailure.failed_at))
                    .limit(limit)
                )
            ).all()
            return [_to_failure_response(row) for row in rows]
        return []

    async def get_health_summary(self) -> IngestionHealthSummaryResponse:
        async for db in get_async_db_session():
            total_jobs = int((await db.scalar(select(func.count(DBIngestionJob.id)))) or 0)
            accepted_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "accepted"
                        )
                    )
                )
                or 0
            )
            queued_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "queued"
                        )
                    )
                )
                or 0
            )
            failed_jobs = int(
                (
                    await db.scalar(
                        select(func.count(DBIngestionJob.id)).where(
                            DBIngestionJob.status == "failed"
                        )
                    )
                )
                or 0
            )
            return IngestionHealthSummaryResponse(
                total_jobs=total_jobs,
                accepted_jobs=accepted_jobs,
                queued_jobs=queued_jobs,
                failed_jobs=failed_jobs,
                backlog_jobs=accepted_jobs + queued_jobs,
            )
        return IngestionHealthSummaryResponse(
            total_jobs=0,
            accepted_jobs=0,
            queued_jobs=0,
            failed_jobs=0,
            backlog_jobs=0,
        )

    async def get_slo_status(
        self,
        *,
        lookback_minutes: int = 60,
        failure_rate_threshold: Decimal = Decimal("0.03"),
        queue_latency_threshold_seconds: float = 5.0,
        backlog_age_threshold_seconds: float = 300.0,
    ) -> IngestionSloStatusResponse:
        async for db in get_async_db_session():
            since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
            jobs = (
                await db.scalars(select(DBIngestionJob).where(DBIngestionJob.submitted_at >= since))
            ).all()
            total_jobs = len(jobs)
            failed_jobs = len([j for j in jobs if j.status == "failed"])

            latencies = [
                (j.completed_at - j.submitted_at).total_seconds()
                for j in jobs
                if j.completed_at is not None
            ]
            latencies.sort()
            if not latencies:
                p95_latency = 0.0
            else:
                p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
                p95_latency = float(latencies[p95_index])

            non_terminal = [j for j in jobs if j.status in {"accepted", "queued"}]
            if non_terminal:
                oldest = min(non_terminal, key=lambda item: item.submitted_at)
                backlog_age_seconds = float(
                    (datetime.now(UTC) - oldest.submitted_at).total_seconds()
                )
            else:
                backlog_age_seconds = 0.0
            INGESTION_BACKLOG_AGE_SECONDS.set(backlog_age_seconds)

            failure_rate = (
                Decimal(failed_jobs) / Decimal(total_jobs)
                if total_jobs
                else Decimal("0")
            )
            return IngestionSloStatusResponse(
                lookback_minutes=lookback_minutes,
                total_jobs=total_jobs,
                failed_jobs=failed_jobs,
                failure_rate=failure_rate,
                p95_queue_latency_seconds=p95_latency,
                backlog_age_seconds=backlog_age_seconds,
                breach_failure_rate=failure_rate > failure_rate_threshold,
                breach_queue_latency=p95_latency > queue_latency_threshold_seconds,
                breach_backlog_age=backlog_age_seconds > backlog_age_threshold_seconds,
            )
        return IngestionSloStatusResponse(
            lookback_minutes=lookback_minutes,
            total_jobs=0,
            failed_jobs=0,
            failure_rate=Decimal("0"),
            p95_queue_latency_seconds=0.0,
            backlog_age_seconds=0.0,
            breach_failure_rate=False,
            breach_queue_latency=False,
            breach_backlog_age=False,
        )

    async def list_consumer_dlq_events(
        self,
        *,
        limit: int = 100,
        original_topic: str | None = None,
        consumer_group: str | None = None,
    ) -> list[ConsumerDlqEventResponse]:
        async for db in get_async_db_session():
            stmt = select(DBConsumerDlqEvent)
            if original_topic:
                stmt = stmt.where(DBConsumerDlqEvent.original_topic == original_topic)
            if consumer_group:
                stmt = stmt.where(DBConsumerDlqEvent.consumer_group == consumer_group)
            rows = (
                await db.scalars(
                    stmt.order_by(desc(DBConsumerDlqEvent.observed_at)).limit(limit)
                )
            ).all()
            return [_to_dlq_event_response(row) for row in rows]
        return []

    async def get_ops_mode(self) -> IngestionOpsModeResponse:
        async for db in get_async_db_session():
            row = await db.scalar(
                select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
            )
            if row is None:
                row = DBIngestionOpsControl(
                    id=1,
                    mode="normal",
                    replay_window_start=None,
                    replay_window_end=None,
                    updated_by="system_bootstrap",
                )
                async with db.begin():
                    db.add(row)
                    await db.flush()
            return IngestionOpsModeResponse(
                mode=row.mode,  # type: ignore[arg-type]
                replay_window_start=row.replay_window_start,
                replay_window_end=row.replay_window_end,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )
        raise RuntimeError("Unable to read ingestion ops mode.")

    async def update_ops_mode(
        self,
        *,
        mode: str,
        replay_window_start: datetime | None,
        replay_window_end: datetime | None,
        updated_by: str | None,
    ) -> IngestionOpsModeResponse:
        async for db in get_async_db_session():
            async with db.begin():
                row = await db.scalar(
                    select(DBIngestionOpsControl).where(DBIngestionOpsControl.id == 1).limit(1)
                )
                if row is None:
                    row = DBIngestionOpsControl(id=1, mode="normal")
                    db.add(row)
                    await db.flush()
                row.mode = mode
                row.replay_window_start = replay_window_start
                row.replay_window_end = replay_window_end
                row.updated_by = updated_by
                row.updated_at = datetime.now(UTC)
            return IngestionOpsModeResponse(
                mode=row.mode,  # type: ignore[arg-type]
                replay_window_start=row.replay_window_start,
                replay_window_end=row.replay_window_end,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            )
        raise RuntimeError("Unable to update ingestion ops mode.")

    async def assert_ingestion_writable(self) -> None:
        mode = await self.get_ops_mode()
        INGESTION_MODE_STATE.set({"normal": 0, "paused": 1, "drain": 2}[mode.mode])
        if mode.mode in {"paused", "drain"}:
            raise PermissionError(
                f"Ingestion is currently in '{mode.mode}' mode and not accepting new requests."
            )

    async def assert_retry_allowed(self, submitted_at: datetime) -> None:
        mode = await self.get_ops_mode()
        if mode.mode == "paused":
            raise PermissionError("Retries are blocked while ingestion is paused.")
        now = datetime.now(UTC)
        if mode.replay_window_start and now < mode.replay_window_start:
            raise PermissionError("Current time is before configured replay window.")
        if mode.replay_window_end and now > mode.replay_window_end:
            raise PermissionError("Current time is after configured replay window.")
        if now < submitted_at:
            raise PermissionError("Retry blocked: job submission timestamp is in the future.")


_INGESTION_JOB_SERVICE = IngestionJobService()


def get_ingestion_job_service() -> IngestionJobService:
    return _INGESTION_JOB_SERVICE
