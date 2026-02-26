# tests/integration/services/ingestion-service/test_ingestion_routers.py
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
import httpx
from io import BytesIO
from openpyxl import Workbook

from src.services.ingestion_service.app.main import app
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer

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

    app.dependency_overrides[get_kafka_producer] = override_get_kafka_producer

    # --- THIS IS THE FIX ---
    # Use ASGITransport for in-process testing instead of making real network calls.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # --- END FIX ---
        yield client

    # Clean up the override after the test
    del app.dependency_overrides[get_kafka_producer]


async def test_ingest_portfolios_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/portfolios endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "portfolios": [
            {
                "portfolioId": "P1",
                "baseCurrency": "USD",
                "openDate": "2025-01-01",
                "cifId": "c",
                "status": "s",
                "riskExposure": "r",
                "investmentTimeHorizon": "i",
                "portfolioType": "t",
                "bookingCenter": "b",
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
    mock_kafka_producer.publish_message.assert_called_once()


async def test_ingest_instruments_endpoint(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    """Tests the POST /ingest/instruments endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = {
        "instruments": [
            {
                "securityId": "S1",
                "name": "N1",
                "isin": "I1",
                "instrumentCurrency": "USD",
                "productType": "E",
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
            {"securityId": "S1", "priceDate": "2025-01-01", "price": 100, "currency": "USD"}
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
            {"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": "2025-01-01", "rate": 0.9}
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
        "sourceSystem": "UI_UPLOAD",
        "mode": "UPSERT",
        "businessDates": [{"businessDate": "2026-01-02"}],
        "portfolios": [
            {
                "portfolioId": "P1",
                "baseCurrency": "USD",
                "openDate": "2025-01-01",
                "cifId": "c",
                "status": "s",
                "riskExposure": "r",
                "investmentTimeHorizon": "i",
                "portfolioType": "t",
                "bookingCenter": "b",
            }
        ],
        "instruments": [
            {
                "securityId": "S1",
                "name": "N1",
                "isin": "I1",
                "instrumentCurrency": "USD",
                "productType": "E",
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
        "marketPrices": [
            {"securityId": "S1", "priceDate": "2026-01-02", "price": 100, "currency": "USD"}
        ],
        "fxRates": [
            {"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": "2026-01-02", "rate": 0.9}
        ],
    }

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["published_counts"]["portfolios"] == 1
    assert body["published_counts"]["transactions"] == 1
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
        "sourceSystem": "UI_UPLOAD",
        "mode": "UPSERT",
    }

    response = await async_test_client.post("/ingest/portfolio-bundle", json=payload)

    assert response.status_code == 422
    assert "at least one non-empty entity list" in response.text
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
        data={"entityType": "transactions", "sampleSize": "10"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["entity_type"] == "transactions"
    assert body["total_rows"] == 2
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 1


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
        data={"entityType": "transactions", "allowPartial": "true"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["published_rows"] == 1
    assert body["skipped_rows"] == 1
    mock_kafka_producer.publish_message.assert_called_once()


async def test_upload_commit_xlsx_rejects_invalid_without_partial(
    async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock
):
    mock_kafka_producer.publish_message.reset_mock()
    xlsx_content = _xlsx_upload_bytes(
        headers=["securityId", "name", "isin", "instrumentCurrency", "productType"],
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
        data={"entityType": "instruments"},
    )

    assert response.status_code == 422
    mock_kafka_producer.publish_message.assert_not_called()
