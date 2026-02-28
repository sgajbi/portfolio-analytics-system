from datetime import datetime
from typing import Any

from app.DTOs.business_date_dto import BusinessDateIngestionRequest
from app.DTOs.fx_rate_dto import FxRateIngestionRequest
from app.DTOs.ingestion_job_dto import (
    ConsumerDlqEventListResponse,
    IngestionHealthSummaryResponse,
    IngestionJobFailureListResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionOpsModeResponse,
    IngestionOpsModeUpdateRequest,
    IngestionRetryRequest,
    IngestionSloStatusResponse,
)
from app.DTOs.instrument_dto import InstrumentIngestionRequest
from app.DTOs.market_price_dto import MarketPriceIngestionRequest
from app.DTOs.portfolio_bundle_dto import PortfolioBundleIngestionRequest
from app.DTOs.portfolio_dto import PortfolioIngestionRequest
from app.DTOs.reprocessing_dto import ReprocessingRequest
from app.DTOs.transaction_dto import TransactionIngestionRequest
from app.request_metadata import get_request_lineage
from app.routers.reprocessing import REPROCESSING_REQUESTED_TOPIC
from app.services.ingestion_job_service import IngestionJobService, get_ingestion_job_service
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

router = APIRouter()


def _filter_payload_by_record_keys(
    *,
    endpoint: str,
    payload: dict[str, Any],
    record_keys: list[str],
) -> dict[str, Any]:
    if not record_keys:
        return payload
    key_set = set(record_keys)
    if endpoint == "/ingest/transactions":
        rows = [
            row
            for row in payload.get("transactions", [])
            if row.get("transaction_id") in key_set
        ]
        return {"transactions": rows}
    if endpoint == "/ingest/portfolios":
        rows = [row for row in payload.get("portfolios", []) if row.get("portfolio_id") in key_set]
        return {"portfolios": rows}
    if endpoint == "/ingest/instruments":
        rows = [row for row in payload.get("instruments", []) if row.get("security_id") in key_set]
        return {"instruments": rows}
    if endpoint == "/ingest/business-dates":
        rows = [
            row
            for row in payload.get("business_dates", [])
            if str(row.get("business_date")) in key_set
        ]
        return {"business_dates": rows}
    if endpoint == "/reprocess/transactions":
        rows = [txn_id for txn_id in payload.get("transaction_ids", []) if txn_id in key_set]
        return {"transaction_ids": rows}
    raise ValueError(
        f"Partial retry is not supported for endpoint '{endpoint}'."
    )


async def _replay_job_payload(
    *,
    endpoint: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    ingestion_service: IngestionService,
    kafka_producer: KafkaProducer,
) -> None:
    if endpoint == "/ingest/transactions":
        request_model = TransactionIngestionRequest.model_validate(payload)
        await ingestion_service.publish_transactions(
            request_model.transactions, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/portfolios":
        request_model = PortfolioIngestionRequest.model_validate(payload)
        await ingestion_service.publish_portfolios(
            request_model.portfolios, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/instruments":
        request_model = InstrumentIngestionRequest.model_validate(payload)
        await ingestion_service.publish_instruments(
            request_model.instruments, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/market-prices":
        request_model = MarketPriceIngestionRequest.model_validate(payload)
        await ingestion_service.publish_market_prices(
            request_model.market_prices, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/fx-rates":
        request_model = FxRateIngestionRequest.model_validate(payload)
        await ingestion_service.publish_fx_rates(
            request_model.fx_rates, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/business-dates":
        request_model = BusinessDateIngestionRequest.model_validate(payload)
        await ingestion_service.publish_business_dates(
            request_model.business_dates, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/ingest/portfolio-bundle":
        request_model = PortfolioBundleIngestionRequest.model_validate(payload)
        await ingestion_service.publish_portfolio_bundle(
            request_model, idempotency_key=idempotency_key
        )
        return
    if endpoint == "/reprocess/transactions":
        request_model = ReprocessingRequest.model_validate(payload)
        correlation_id, _, _ = get_request_lineage()
        headers: list[tuple[str, bytes]] = []
        if correlation_id:
            headers.append(("correlation_id", correlation_id.encode("utf-8")))
        if idempotency_key:
            headers.append(("idempotency_key", idempotency_key.encode("utf-8")))
        for txn_id in request_model.transaction_ids:
            kafka_producer.publish_message(
                topic=REPROCESSING_REQUESTED_TOPIC,
                key=txn_id,
                value={"transaction_id": txn_id},
                headers=headers or None,
            )
        kafka_producer.flush(timeout=5)
        return
    raise ValueError(f"Retry not supported for endpoint '{endpoint}'.")


@router.get(
    "/ingestion/jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion job status",
    description="Returns ingestion job lifecycle status and operational metadata by job_id.",
)
async def get_ingestion_job(
    job_id: str,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    job = await ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    return job


@router.get(
    "/ingestion/jobs",
    response_model=IngestionJobListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion jobs",
    description=(
        "Returns ingestion jobs for operational monitoring with status/entity/date filters "
        "and cursor pagination."
    ),
)
async def list_ingestion_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    entity_type: str | None = Query(default=None),
    submitted_from: datetime | None = Query(default=None, alias="from"),
    submitted_to: datetime | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    status_value = status_filter if status_filter in {"accepted", "queued", "failed"} else None
    jobs, next_cursor = await ingestion_job_service.list_jobs(
        status=status_value,
        entity_type=entity_type,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
        cursor=cursor,
        limit=limit,
    )
    return IngestionJobListResponse(jobs=jobs, total=len(jobs), next_cursor=next_cursor)


@router.get(
    "/ingestion/jobs/{job_id}/failures",
    response_model=IngestionJobFailureListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List ingestion job failures",
    description="Returns failure history captured for an ingestion job.",
)
async def list_ingestion_job_failures(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    job = await ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    failures = await ingestion_job_service.list_failures(job_id=job_id, limit=limit)
    return IngestionJobFailureListResponse(failures=failures, total=len(failures))


@router.post(
    "/ingestion/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Retry a failed ingestion job",
    description=(
        "Replays full or partial stored payload for a failed ingestion job."
    ),
)
async def retry_ingestion_job(
    job_id: str,
    retry_request: IngestionRetryRequest = Body(default_factory=IngestionRetryRequest),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    kafka_producer: KafkaProducer = Depends(get_kafka_producer),
):
    context = await ingestion_job_service.get_job_replay_context(job_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found.",
            },
        )
    if context.request_payload is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INGESTION_JOB_RETRY_UNSUPPORTED",
                "message": (
                    f"Ingestion job '{job_id}' does not have stored request payload and "
                    "cannot be retried."
                ),
            },
        )
    try:
        await ingestion_job_service.assert_retry_allowed(context.submitted_at)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INGESTION_RETRY_BLOCKED", "message": str(exc)},
        ) from exc

    try:
        replay_payload = _filter_payload_by_record_keys(
            endpoint=context.endpoint,
            payload=context.request_payload,
            record_keys=retry_request.record_keys,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INGESTION_PARTIAL_RETRY_UNSUPPORTED", "message": str(exc)},
        ) from exc

    if retry_request.dry_run:
        job = await ingestion_job_service.get_job(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "INGESTION_JOB_NOT_FOUND",
                    "message": f"Ingestion job '{job_id}' was not found after dry-run.",
                },
            )
        return job

    try:
        await _replay_job_payload(
            endpoint=context.endpoint,
            payload=replay_payload,
            idempotency_key=context.idempotency_key,
            ingestion_service=ingestion_service,
            kafka_producer=kafka_producer,
        )
        await ingestion_job_service.mark_retried(job_id)
        await ingestion_job_service.mark_queued(job_id)
    except Exception as exc:
        await ingestion_job_service.mark_failed(
            job_id,
            str(exc),
            failure_phase="retry_publish",
            failed_record_keys=retry_request.record_keys,
        )
        raise

    job = await ingestion_job_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "INGESTION_JOB_NOT_FOUND",
                "message": f"Ingestion job '{job_id}' was not found after retry.",
            },
        )
    return job


@router.get(
    "/ingestion/health/summary",
    response_model=IngestionHealthSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operational health summary",
    description="Returns aggregate ingestion job health counters for operations.",
)
async def get_ingestion_health_summary(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_health_summary()


@router.get(
    "/ingestion/health/lag",
    response_model=IngestionHealthSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion backlog indicators",
    description="Returns ingestion lag indicators derived from accepted and queued jobs.",
)
async def get_ingestion_health_lag(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_health_summary()


@router.get(
    "/ingestion/health/slo",
    response_model=IngestionSloStatusResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Evaluate ingestion SLO status",
    description=(
        "Evaluates ingestion failure-rate, queue latency, and backlog-age indicators "
        "for alert-ready operations visibility."
    ),
)
async def get_ingestion_slo_status(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    failure_rate_threshold: float = Query(default=0.03, ge=0, le=1),
    queue_latency_threshold_seconds: float = Query(default=5.0, ge=0.1, le=600),
    backlog_age_threshold_seconds: float = Query(default=300, ge=1, le=86400),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_slo_status(
        lookback_minutes=lookback_minutes,
        failure_rate_threshold=failure_rate_threshold,
        queue_latency_threshold_seconds=queue_latency_threshold_seconds,
        backlog_age_threshold_seconds=backlog_age_threshold_seconds,
    )


@router.get(
    "/ingestion/dlq/consumer-events",
    response_model=ConsumerDlqEventListResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="List consumer dead-letter events",
    description="Returns persistence consumer DLQ events for API-first operational triage.",
)
async def list_consumer_dlq_events(
    limit: int = Query(default=100, ge=1, le=500),
    original_topic: str | None = Query(default=None),
    consumer_group: str | None = Query(default=None),
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    events = await ingestion_job_service.list_consumer_dlq_events(
        limit=limit, original_topic=original_topic, consumer_group=consumer_group
    )
    return ConsumerDlqEventListResponse(events=events, total=len(events))


@router.get(
    "/ingestion/ops/control",
    response_model=IngestionOpsModeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Get ingestion operations control mode",
    description="Returns current ingestion mode (normal/paused/drain) and retry replay window.",
)
async def get_ingestion_ops_control(
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    return await ingestion_job_service.get_ops_mode()


@router.put(
    "/ingestion/ops/control",
    response_model=IngestionOpsModeResponse,
    status_code=status.HTTP_200_OK,
    tags=["Ingestion Operations"],
    summary="Update ingestion operations control mode",
    description="Updates ingestion mode and optional replay window for runbook operations.",
)
async def update_ingestion_ops_control(
    update_request: IngestionOpsModeUpdateRequest,
    ingestion_job_service: IngestionJobService = Depends(get_ingestion_job_service),
):
    if (
        update_request.replay_window_start
        and update_request.replay_window_end
        and update_request.replay_window_start > update_request.replay_window_end
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INGESTION_INVALID_REPLAY_WINDOW",
                "message": "replay_window_start must be before replay_window_end.",
            },
        )
    return await ingestion_job_service.update_ops_mode(
        mode=update_request.mode,
        replay_window_start=update_request.replay_window_start,
        replay_window_end=update_request.replay_window_end,
        updated_by=update_request.updated_by,
    )
