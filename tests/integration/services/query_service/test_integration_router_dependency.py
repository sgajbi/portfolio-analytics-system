from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app
from src.services.query_service.app.routers.integration import (
    IntegrationService,
    get_integration_service,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_service = AsyncMock()
    app.dependency_overrides[get_integration_service] = lambda: mock_service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mock_service
    app.dependency_overrides.pop(get_integration_service, None)


def snapshot_request_payload() -> dict:
    return {
        "asOfDate": "2026-02-23",
        "includeSections": ["OVERVIEW", "HOLDINGS"],
        "consumerSystem": "lotus-performance",
    }


def performance_input_request_payload() -> dict:
    return {
        "asOfDate": "2026-02-23",
        "lookbackDays": 365,
        "consumerSystem": "lotus-performance",
    }


async def test_integration_snapshot_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.return_value = {
        "contractVersion": "v1",
        "consumerSystem": "lotus-performance",
        "portfolio": {
            "portfolio_id": "P1",
            "base_currency": "USD",
            "open_date": date(2025, 1, 1),
            "close_date": None,
            "risk_exposure": "MODERATE",
            "investment_time_horizon": "LONG_TERM",
            "portfolio_type": "DISCRETIONARY",
            "objective": "GROWTH",
            "booking_center": "LON-01",
            "cif_id": "CIF-1",
            "is_leverage_allowed": False,
            "advisor_id": "ADV-1",
            "status": "ACTIVE",
        },
        "snapshot": {
            "portfolio_id": "P1",
            "as_of_date": date(2026, 2, 23),
            "overview": None,
            "allocation": None,
            "performance": None,
            "riskAnalytics": None,
            "incomeAndActivity": None,
            "holdings": None,
            "transactions": None,
        },
        "metadata": {
            "generatedAt": datetime(2026, 2, 24, tzinfo=UTC),
            "sourceAsOfDate": date(2026, 2, 23),
            "freshnessStatus": "FRESH",
            "lineageRefs": {
                "portfolioId": "P1",
                "asOfDate": date(2026, 2, 23),
                "correlationId": "QRY-123",
            },
            "sectionGovernance": {
                "requestedSections": ["OVERVIEW", "HOLDINGS"],
                "effectiveSections": ["OVERVIEW", "HOLDINGS"],
                "droppedSections": [],
                "warnings": [],
            },
            "policyProvenance": {
                "policyVersion": "tenant-default-v2",
                "policySource": "global",
                "matchedRuleId": "global.consumers.lotus-performance",
                "strictMode": False,
            },
        },
    }

    response = await client.post(
        "/integration/portfolios/P1/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 200
    assert response.json()["contractVersion"] == "v1"
    assert response.json()["metadata"]["freshnessStatus"] == "FRESH"
    assert response.json()["metadata"]["policyProvenance"]["policyVersion"] == "tenant-default-v2"
    assert "X-Correlation-ID" in response.headers


async def test_integration_snapshot_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.side_effect = ValueError("Portfolio not found")

    response = await client.post(
        "/integration/portfolios/P404/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_integration_snapshot_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.side_effect = RuntimeError("boom")

    response = await client.post(
        "/integration/portfolios/P500/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 500
    assert "integration snapshot" in response.json()["detail"].lower()


async def test_integration_snapshot_policy_rejection_maps_to_403(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_core_snapshot.side_effect = PermissionError("sections not allowed")

    response = await client.post(
        "/integration/portfolios/P1/core-snapshot", json=snapshot_request_payload()
    )

    assert response.status_code == 403
    assert "allowed" in response.json()["detail"].lower()


async def test_effective_policy_endpoint_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_effective_policy = MagicMock(
        return_value={
            "contractVersion": "v1",
            "sourceService": "lotus-core",
            "consumerSystem": "lotus-performance",
            "tenantId": "tenant-a",
            "generatedAt": datetime(2026, 2, 24, tzinfo=UTC),
            "policyProvenance": {
                "policyVersion": "tenant-a-v3",
                "policySource": "tenant",
                "matchedRuleId": "tenant.tenant-a.consumers.lotus-performance",
                "strictMode": False,
            },
            "allowedSections": ["OVERVIEW", "HOLDINGS"],
            "warnings": [],
        }
    )

    response = await client.get(
        "/integration/policy/effective?consumerSystem=lotus-performance&tenantId=tenant-a&includeSections=OVERVIEW&includeSections=HOLDINGS"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["policyProvenance"]["policySource"] == "tenant"
    assert payload["allowedSections"] == ["OVERVIEW", "HOLDINGS"]
    mock_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-performance",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW", "HOLDINGS"],
    )


async def test_performance_input_success(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_performance_input.return_value = {
        "contractVersion": "v1",
        "sourceService": "lotus-core",
        "consumerSystem": "lotus-performance",
        "portfolioId": "P1",
        "baseCurrency": "USD",
        "performanceStartDate": "2026-01-01",
        "asOfDate": "2026-02-23",
        "valuationPoints": [
            {
                "day": 1,
                "perfDate": "2026-01-01",
                "beginMv": 100.0,
                "bodCf": 0.0,
                "eodCf": 0.0,
                "mgmtFees": 0.0,
                "endMv": 101.0,
            }
        ],
    }

    response = await client.post(
        "/integration/portfolios/P1/performance-input",
        json=performance_input_request_payload(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["portfolioId"] == "P1"
    assert payload["valuationPoints"][0]["endMv"] == 101.0


async def test_performance_input_not_found_maps_to_404(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_performance_input.side_effect = ValueError("No rows")

    response = await client.post(
        "/integration/portfolios/P404/performance-input",
        json=performance_input_request_payload(),
    )

    assert response.status_code == 404
    assert "no rows" in response.json()["detail"].lower()


async def test_performance_input_unexpected_maps_to_500(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_portfolio_performance_input.side_effect = RuntimeError("boom")

    response = await client.post(
        "/integration/portfolios/P500/performance-input",
        json=performance_input_request_payload(),
    )

    assert response.status_code == 500
    assert "performance input series" in response.json()["detail"].lower()


async def test_effective_policy_permission_error_maps_to_403(async_test_client):
    client, mock_service = async_test_client
    mock_service.get_effective_policy = MagicMock(side_effect=PermissionError("forbidden"))

    response = await client.get(
        "/integration/policy/effective?consumerSystem=lotus-performance&tenantId=tenant-a&includeSections=OVERVIEW"
    )

    assert response.status_code == 403
    assert "forbidden" in response.json()["detail"].lower()


async def test_get_integration_service_dependency_factory():
    db = AsyncMock(spec=AsyncSession)

    service = get_integration_service(db)

    assert isinstance(service, IntegrationService)
