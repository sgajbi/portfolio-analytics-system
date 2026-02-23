from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from src.services.query_service.app.dtos.fx_rate_dto import FxRateResponse
from src.services.query_service.app.dtos.instrument_dto import PaginatedInstrumentResponse
from src.services.query_service.app.dtos.price_dto import MarketPriceResponse
from src.services.query_service.app.main import app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def async_test_client():
    mock_fx_service = MagicMock()
    mock_fx_service.get_fx_rates = AsyncMock(
        return_value=FxRateResponse(from_currency="USD", to_currency="SGD", rates=[])
    )
    mock_instrument_service = MagicMock()
    mock_instrument_service.get_instruments = AsyncMock(
        return_value=PaginatedInstrumentResponse(total=0, skip=0, limit=50, instruments=[])
    )
    mock_price_service = MagicMock()
    mock_price_service.get_prices = AsyncMock(
        return_value=MarketPriceResponse(security_id="SEC_1", prices=[])
    )

    app.dependency_overrides[get_async_db_session] = lambda: AsyncMock(spec=AsyncSession)

    with (
        patch(
            "src.services.query_service.app.routers.fx_rates.FxRateService",
            return_value=mock_fx_service,
        ),
        patch(
            "src.services.query_service.app.routers.instruments.InstrumentService",
            return_value=mock_instrument_service,
        ),
        patch(
            "src.services.query_service.app.routers.prices.MarketPriceService",
            return_value=mock_price_service,
        ),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, mock_fx_service, mock_instrument_service, mock_price_service

    app.dependency_overrides.pop(get_async_db_session, None)


async def test_get_fx_rates_success_and_uppercase(async_test_client):
    client, mock_fx_service, _, _ = async_test_client

    response = await client.get(
        "/fx-rates/",
        params={
            "from_currency": "usd",
            "to_currency": "sgd",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["from_currency"] == "USD"
    assert response.json()["to_currency"] == "SGD"
    mock_fx_service.get_fx_rates.assert_awaited_once_with(
        from_currency="USD",
        to_currency="SGD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )


async def test_get_instruments_success_with_pagination(async_test_client):
    client, _, mock_instrument_service, _ = async_test_client

    response = await client.get(
        "/instruments/",
        params={"security_id": "SEC_1", "product_type": "Equity", "skip": 10, "limit": 25},
    )

    assert response.status_code == 200
    mock_instrument_service.get_instruments.assert_awaited_once_with(
        security_id="SEC_1",
        product_type="Equity",
        skip=10,
        limit=25,
    )


async def test_get_prices_success(async_test_client):
    client, _, _, mock_price_service = async_test_client

    response = await client.get(
        "/prices/",
        params={
            "security_id": "SEC_1",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["security_id"] == "SEC_1"
    mock_price_service.get_prices.assert_awaited_once_with(
        security_id="SEC_1",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )
