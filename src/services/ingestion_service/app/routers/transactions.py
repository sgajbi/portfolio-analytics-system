import logging
from typing import Annotated

from app.ack_response import build_batch_ack, build_single_ack
from app.DTOs.ingestion_ack_dto import BatchIngestionAcceptedResponse, IngestionAcceptedResponse
from app.DTOs.transaction_dto import Transaction, TransactionIngestionRequest
from app.request_metadata import resolve_idempotency_key
from app.services.ingestion_service import IngestionService, get_ingestion_service
from fastapi import APIRouter, Depends, Header, Request, status

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest/transaction",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionAcceptedResponse,
    tags=["Transactions"],
    summary="Ingest a single transaction",
    description=("Accepts a canonical transaction and publishes it for asynchronous processing."),
)
async def ingest_transaction(
    transaction: Transaction,
    request: Request,
    idempotency_key_header: Annotated[
        str | None,
        Header(
            alias="X-Idempotency-Key",
            description=(
                "Optional idempotency key to make retries safe for the same logical request."
            ),
        ),
    ] = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(request)
    logger.info(
        "Received single transaction.",
        extra={
            "transaction_id": transaction.transaction_id,
            "portfolio_id": transaction.portfolio_id,
            "idempotency_key": idempotency_key,
        },
    )

    await ingestion_service.publish_transaction(transaction, idempotency_key=idempotency_key)

    logger.info(
        "Transaction successfully queued.", extra={"transaction_id": transaction.transaction_id}
    )
    return build_single_ack(
        message="Transaction accepted for asynchronous ingestion processing.",
        entity_type="transaction",
        idempotency_key=idempotency_key,
    )


@router.post(
    "/ingest/transactions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchIngestionAcceptedResponse,
    tags=["Transactions"],
    summary="Ingest a transaction batch",
    description=(
        "Accepts a batch of canonical transactions and publishes them for asynchronous processing."
    ),
)
async def ingest_transactions(
    request: TransactionIngestionRequest,
    http_request: Request,
    idempotency_key_header: Annotated[
        str | None,
        Header(
            alias="X-Idempotency-Key",
            description=(
                "Optional idempotency key to make retries safe for the same logical request."
            ),
        ),
    ] = None,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    idempotency_key = idempotency_key_header or resolve_idempotency_key(http_request)
    num_transactions = len(request.transactions)
    logger.info(
        "Received request to ingest transactions.",
        extra={"num_transactions": num_transactions, "idempotency_key": idempotency_key},
    )

    await ingestion_service.publish_transactions(
        request.transactions, idempotency_key=idempotency_key
    )

    logger.info("Transactions successfully queued.", extra={"num_transactions": num_transactions})
    return build_batch_ack(
        message="Transactions accepted for asynchronous ingestion processing.",
        entity_type="transaction",
        accepted_count=num_transactions,
        idempotency_key=idempotency_key,
    )
