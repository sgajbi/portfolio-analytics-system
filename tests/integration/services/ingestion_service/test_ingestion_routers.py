# tests/integration/services/ingestion-service/test_ingestion_routers.py
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from openpyxl import Workbook
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer

from src.services.ingestion_service.app.DTOs.ingestion_job_dto import IngestionJobResponse
from src.services.ingestion_service.app.main import app
from src.services.ingestion_service.app.routers import (
    business_dates as business_dates_router,
)
from src.services.ingestion_service.app.routers import (
    fx_rates as fx_rates_router,
)
from src.services.ingestion_service.app.routers import (
    ingestion_jobs as ingestion_jobs_router,
)
from src.services.ingestion_service.app.routers import (
    instruments as instruments_router,
)
from src.services.ingestion_service.app.routers import (
    market_prices as market_prices_router,
)
from src.services.ingestion_service.app.routers import (
    portfolio_bundle as portfolio_bundle_router,
)
from src.services.ingestion_service.app.routers import (
    portfolios as portfolios_router,
)
from src.services.ingestion_service.app.routers import (
    reprocessing as reprocessing_router,
)
from src.services.ingestion_service.app.routers import (
    transactions as transactions_router,
)
from src.services.ingestion_service.app.services.ingestion_job_service import (
    get_ingestion_job_service,
)

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    return mock


@pytest_asyncio.fixture
async def async_test_client(mock_kafka_producer: MagicMock):
    """
    Provides an httpx.AsyncClient with the KafkaProducer dependency replaced by a MagicMock.
    """

    def override_get_kafka_producer():
        return mock_kafka_producer

    class FakeIngestionJobService:
        def __init__(self):
            self.jobs: dict[str, IngestionJobResponse] = {}

        async def create_job(
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
            self.jobs[job_id] = IngestionJobResponse(
                job_id=job_id,
                endpoint=endpoint,
                entity_type=entity_type,
                status="accepted",
                accepted_count=accepted_count,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_id=request_id,
                trace_id=trace_id,
                submitted_at=datetime.now(UTC),
                completed_at=None,
                failure_reason=None,
            )

        async def mark_queued(self, job_id: str) -> None:
            if job_id not in self.jobs:
                return
            record = self.jobs[job_id]
            record.status = "queued"
            record.completed_at = datetime.now(UTC)
            self.jobs[job_id] = record

        async def mark_failed(self, job_id: str, failure_reason: str) -> None:
            if job_id not in self.jobs:
                return
            record = self.jobs[job_id]
            record.status = "failed"
            record.failure_reason = failure_reason
            record.completed_at = datetime.now(UTC)
            self.jobs[job_id] = record

        async def get_job(self, job_id: str) -> IngestionJobResponse | None:
            return self.jobs.get(job_id)

        async def list_jobs(
            self,
            *,
            status: str | None = None,
            entity_type: str | None = None,
            limit: int = 100,
        ) -> list[IngestionJobResponse]:
            values = list(self.jobs.values())
            filtered = [
                job
                for job in values
                if (status is None or job.status == status)
                and (entity_type is None or job.entity_type == entity_type)
            ]
            return filtered[:limit]

    fake_job_service = FakeIngestionJobService()
    app.dependency_overrides[get_ingestion_job_service] = lambda: fake_job_service
    app.dependency_overrides[transactions_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[portfolios_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[instruments_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[market_prices_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[fx_rates_router.get_ingestion_job_service] = lambda: fake_job_service
    app.dependency_overrides[business_dates_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[portfolio_bundle_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[reprocessing_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )
    app.dependency_overrides[ingestion_jobs_router.get_ingestion_job_service] = (
        lambda: fake_job_service
    )

    app.dependency_overrides[get_kafka_producer] = override_get_kafka_producer

    # --- THIS IS THE FIX ---
    # Use ASGITransport for in-process testing instead of making real network calls.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # --- END FIX ---
        yield client

    # Clean up the override after the test
    app.dependency_overrides.pop(get_kafka_producer, None)
    app.dependency_overrides.pop(get_ingestion_job_service, None)
    app.dependency_overrides.pop(transactions_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(portfolios_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(instruments_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(market_prices_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(fx_rates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(business_dates_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(portfolio_bundle_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(reprocessing_router.get_ingestion_job_service, None)
    app.dependency_overrides.pop(ingestion_jobs_router.get_ingestion_job_service, None)


async def test_ingest_portfolios_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolios endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "s",
                "risk_exposure": "r",
                "investment_time_horizon": "i",
                "portfolio_type": "t",
                "booking_center_code": "b",
            }
        ]
    }

    response = await async_test_client.post("/ingest/portfolios", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_transactions_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/transactions endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    response = await async_test_client.post("/ingest/transactions", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "transaction"
    assert body["accepted_count"] == 1
    assert "job_id" in body
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingestion_jobs_status_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "transactions": [
            {
                "transaction_id": "T100",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2025-08-12T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    ingest_response = await async_test_client.post("/ingest/transactions", json=payload)
    assert ingest_response.status_code == 202
    job_id = ingest_response.json()["job_id"]

    job_response = await async_test_client.get(f"/ingestion/jobs/{job_id}")
    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["job_id"] == job_id
    assert job_body["status"] == "queued"
    assert job_body["entity_type"] == "transaction"


async def test_ingestion_jobs_list_endpoint(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/jobs", params={"limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert "total" in body


async def test_ingestion_job_not_found(async_test_client: httpx.AsyncClient):
    response = await async_test_client.get("/ingestion/jobs/job_missing_001")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"]["code"] == "INGESTION_JOB_NOT_FOUND"


async def test_ingest_instruments_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/instruments endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "instruments": [
            {
                "security_id": "S1",
                "name": "N1",
                "isin": "I1",
                "currency": "USD",
                "product_type": "E",
            }
        ]
    }

    response = await async_test_client.post("/ingest/instruments", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_market_prices_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/market-prices endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "market_prices": [
            {"security_id": "S1", "price_date": "2025-01-01", "price": 100, "currency": "USD"}
        ]
    }

    response = await async_test_client.post("/ingest/market-prices", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_fx_rates_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/fx-rates endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "fx_rates": [
            {"from_currency": "USD", "to_currency": "EUR", "rate_date": "2025-01-01", "rate": 0.9}
        ]
    }

    response = await async_test_client.post("/ingest/fx-rates", json=payload)

    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_portfolio_bundle_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolio-bundle endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
        "business_dates": [{"business_date": "2026-01-02"}],
        "portfolios": [
            {
                "portfolio_id": "P1",
                "base_currency": "USD",
                "open_date": "2025-01-01",
                "client_id": "c",
                "status": "s",
                "risk_exposure": "r",
                "investment_time_horizon": "i",
                "portfolio_type": "t",
                "booking_center_code": "b",
            }
        ],
        "instruments": [
            {
                "security_id": "S1",
                "name": "N1",
                "isin": "I1",
                "currency": "USD",
                "product_type": "E",
            }
        ],
        "transactions": [
            {
                "transaction_id": "T1",
                "portfolio_id": "P1",
                "instrument_id": "I1",
                "security_id": "S1",
                "transaction_date": "2026-01-02T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 1,
                "price": 1,
                "gross_transaction_amount": 1,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ],
        "market_prices": [
            {"security_id": "S1", "price_date": "2026-01-02", "price": 100, "currency": "USD"}
        ],
        "fx_rates": [
            {"from_currency": "USD", "to_currency": "EUR", "rate_date": "2026-01-02", "rate": 0.9}
        ],
    }

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == "portfolio_bundle"
    assert body["accepted_count"] == 6
    assert "job_id" in body
    assert mock_kafka_producer.publish_message.call_count == 6


async def test_ingest_portfolio_bundle_rejects_empty_payload(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    response = await async_test_client.post("/ingest/portfolio-bundle", json={})

    assert response.status_code == 422
    assert "at least one non-empty entity list" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_rejects_metadata_only_payload(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    payload = {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
    }

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 422
    assert "at least one non-empty entity list" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_ingest_portfolio_bundle_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "false")
    payload = {
        "source_system": "UI_UPLOAD",
        "mode": "UPSERT",
        "business_dates": [{"business_date": "2026-01-02"}],
    }
    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.portfolio_bundle_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


def _xlsx_upload_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


async def test_upload_preview_transactions_csv(async_test_client: httpx.AsyncClient):
    csv_content = "\n".join(
        [
            "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
            "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
            "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
        ]
    ).encode("utf-8")

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "transactions"
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 1


async def test_upload_preview_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    csv_content = b"transaction_id,portfolio_id\nT1,P1"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.bulk_upload_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_transactions_csv_partial(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    csv_content = "\n".join(
        [
            "transaction_id,portfolio_id,instrument_id,security_id,transaction_date,transaction_type,quantity,price,gross_transaction_amount,trade_currency,currency",
            "T1,P1,I1,S1,2026-01-02T10:00:00Z,BUY,10,100,1000,USD,USD",
            "T2,P1,I1,S1,INVALID_DATE,BUY,10,100,1000,USD,USD",
        ]
    ).encode("utf-8")

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "true"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["published_rows"] == 1
    assert body["skipped_rows"] == 1
    mock_kafka_producer.publish_message.assert_called_once()


async def test_upload_commit_disabled_by_feature_flag(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock, monkeypatch
):
    monkeypatch.setenv("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "false")
    csv_content = b"transaction_id,portfolio_id\nT1,P1"
    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("transactions.csv", csv_content, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "true"},
    )

    assert response.status_code == 410
    body = response.json()
    assert body["detail"]["code"] == "LOTUS_CORE_ADAPTER_MODE_DISABLED"
    assert body["detail"]["capability"] == "lotus_core.ingestion.bulk_upload_adapter"
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_xlsx_rejects_invalid_without_partial(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    xlsx_content = _xlsx_upload_bytes(
        headers=["security_id", "name", "isin", "currency", "product_type"],
        rows=[
            ["SEC1", "Bond A", "ISIN1", "USD", "Bond"],
            ["SEC2", "", "ISIN2", "USD", "Bond"],
        ],
    )

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={
            "file": (
                "instruments.xlsx",
                xlsx_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments"},
    )

    assert response.status_code == 422
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_preview_rejects_malformed_xlsx(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    fake_xlsx = b"not-a-real-xlsx"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={
            "file": (
                "fake.xlsx",
                fake_xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments", "sample_size": "10"},
    )

    assert response.status_code == 400
    assert "Invalid XLSX content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_preview_rejects_bad_encoding_csv(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    bad_csv = b"transaction_id,portfolio_id\n\xff\xfe\xfd,PORT1"

    response = await async_test_client.post(
        "/ingest/uploads/preview",
        files={"file": ("bad-encoding.csv", bad_csv, "text/csv")},
        data={"entity_type": "transactions", "sample_size": "10"},
    )

    assert response.status_code == 400
    assert "Invalid CSV content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_rejects_malformed_xlsx(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    fake_xlsx = b"not-a-real-xlsx"

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={
            "file": (
                "fake.xlsx",
                fake_xlsx,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"entity_type": "instruments", "allow_partial": "false"},
    )

    assert response.status_code == 400
    assert "Invalid XLSX content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_upload_commit_rejects_bad_encoding_csv(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    bad_csv = b"transaction_id,portfolio_id\n\xff\xfe\xfd,PORT1"

    response = await async_test_client.post(
        "/ingest/uploads/commit",
        files={"file": ("bad-encoding.csv", bad_csv, "text/csv")},
        data={"entity_type": "transactions", "allow_partial": "false"},
    )

    assert response.status_code == 400
    assert "Invalid CSV content" in response.text
    mock_kafka_producer.publish_message.assert_not_called()


async def test_reprocess_transactions_rejects_empty_transaction_ids(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()

    response = await async_test_client.post(
        "/reprocess/transactions",
        json={"transaction_ids": []},
    )

    assert response.status_code == 422
    mock_kafka_producer.publish_message.assert_not_called()


@pytest.mark.parametrize(
    ("path", "payload", "entity_type"),
    [
        (
            "/ingest/portfolios",
            {
                "portfolios": [
                    {
                        "portfolio_id": "P1",
                        "base_currency": "USD",
                        "open_date": "2025-01-01",
                        "client_id": "c",
                        "status": "s",
                        "risk_exposure": "r",
                        "investment_time_horizon": "i",
                        "portfolio_type": "t",
                        "booking_center_code": "b",
                    }
                ]
            },
            "portfolio",
        ),
        (
            "/ingest/transactions",
            {
                "transactions": [
                    {
                        "transaction_id": "T1",
                        "portfolio_id": "P1",
                        "instrument_id": "I1",
                        "security_id": "S1",
                        "transaction_date": "2025-08-12T10:00:00Z",
                        "transaction_type": "BUY",
                        "quantity": 1,
                        "price": 1,
                        "gross_transaction_amount": 1,
                        "trade_currency": "USD",
                        "currency": "USD",
                    }
                ]
            },
            "transaction",
        ),
        (
            "/ingest/instruments",
            {
                "instruments": [
                    {
                        "security_id": "S1",
                        "name": "N1",
                        "isin": "I1",
                        "currency": "USD",
                        "product_type": "E",
                    }
                ]
            },
            "instrument",
        ),
        (
            "/ingest/market-prices",
            {
                "market_prices": [
                    {
                        "security_id": "S1",
                        "price_date": "2025-01-01",
                        "price": 100,
                        "currency": "USD",
                    }
                ]
            },
            "market_price",
        ),
        (
            "/ingest/fx-rates",
            {
                "fx_rates": [
                    {
                        "from_currency": "USD",
                        "to_currency": "EUR",
                        "rate_date": "2025-01-01",
                        "rate": 0.9,
                    }
                ]
            },
            "fx_rate",
        ),
        (
            "/ingest/business-dates",
            {"business_dates": [{"business_date": "2025-01-01"}]},
            "business_date",
        ),
    ],
)
async def test_ingestion_endpoints_return_canonical_ack_contract(
    async_test_client: httpx.AsyncClient,
    path: str,
    payload: dict,
    entity_type: str,
):
    response = await async_test_client.post(
        path,
        json=payload,
        headers={"X-Idempotency-Key": "integration-ingestion-idempotency-001"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["entity_type"] == entity_type
    assert body["accepted_count"] >= 1
    assert body["idempotency_key"] == "integration-ingestion-idempotency-001"
    assert body["correlation_id"]
    assert body["request_id"]
    assert body["trace_id"]
    assert "job_id" in body
