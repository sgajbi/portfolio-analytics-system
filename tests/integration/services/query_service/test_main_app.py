from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_middleware_preserves_incoming_correlation_id(async_test_client):
    response = await async_test_client.get("/openapi.json", headers={"X-Correlation-ID": "corr-123"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "corr-123"


async def test_middleware_generates_correlation_id_when_missing(async_test_client):
    with patch("src.services.query_service.app.main.generate_correlation_id", return_value="QRY-abc"):
        response = await async_test_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "QRY-abc"


async def test_global_exception_handler_returns_standard_payload(async_test_client):
    async def boom():
        raise RuntimeError("boom")

    app.add_api_route("/_test_raise", boom, methods=["GET"])
    try:
        response = await async_test_client.get("/_test_raise", headers={"X-Correlation-ID": "corr-500"})
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/_test_raise"]

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    assert body["correlation_id"] == "corr-500"
