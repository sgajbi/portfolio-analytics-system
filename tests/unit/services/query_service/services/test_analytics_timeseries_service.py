from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsWindow,
    PageRequest,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_service.app.services.analytics_timeseries_service import (
    AnalyticsInputError,
    AnalyticsTimeseriesService,
)


def make_service() -> AnalyticsTimeseriesService:
    return AnalyticsTimeseriesService(MagicMock(spec=AsyncSession))


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_happy_path() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
                client_id="CIF_123",
                booking_center_code="SGPB",
                portfolio_type="discretionary",
                objective="Balanced growth",
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    bod_cashflow=Decimal("1"),
                    eod_cashflow=Decimal("2"),
                    fees=Decimal("-0.5"),
                    epoch=0,
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
    )

    response = await service.get_portfolio_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            reporting_currency="EUR",
        ),
    )

    assert response.portfolio_id == "DEMO_DPM_EUR_001"
    assert response.observations[0].beginning_market_value == Decimal("100")
    assert len(response.observations[0].cash_flows) == 3


@pytest.mark.asyncio
async def test_get_position_timeseries_paging_token_generation() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                ),
                SimpleNamespace(
                    security_id="SEC_B",
                    valuation_date=date(2025, 1, 2),
                    bod_market_value=Decimal("20"),
                    eod_market_value=Decimal("21"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("2"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Healthcare",
                    country="US",
                    position_currency="USD",
                ),
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )

    response = await service.get_position_timeseries(
        portfolio_id="DEMO_DPM_EUR_001",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            page=PageRequest(page_size=1),
        ),
    )

    assert len(response.rows) == 1
    assert response.page.next_page_token is not None


@pytest.mark.asyncio
async def test_invalid_page_token_raises_invalid_request() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="DEMO_DPM_EUR_001",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="DEMO_DPM_EUR_001",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
                page=PageRequest(page_size=100, page_token="invalid"),
            ),
        )
    assert exc_info.value.code == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_get_portfolio_reference_not_found() -> None:
    service = make_service()
    service.repo = SimpleNamespace(get_portfolio=AsyncMock(return_value=None))

    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_reference(
            portfolio_id="UNKNOWN",
            request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-12-31"),
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_portfolio_reference_success() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
                client_id="CIF_1",
                booking_center_code="SGPB",
                portfolio_type="advisory",
                objective="Growth",
            )
        ),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
    )
    response = await service.get_portfolio_reference(
        portfolio_id="P1",
        request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-12-31"),
    )
    assert response.portfolio_id == "P1"
    assert response.performance_end_date == date(2025, 12, 31)


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_period_resolution_and_missing_fx() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_portfolio_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    valuation_date=date(2025, 1, 31),
                    bod_market_value=Decimal("100"),
                    eod_market_value=Decimal("110"),
                    bod_cashflow=Decimal("0"),
                    eod_cashflow=Decimal("0"),
                    fees=Decimal("0"),
                    epoch=0,
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
        get_latest_portfolio_timeseries_date=AsyncMock(return_value=date(2025, 12, 31)),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="P1",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_year",
                reporting_currency="USD",
            ),
        )
    assert exc_info.value.code == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_get_position_timeseries_with_cash_flows_and_cursor() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("1"),
                    eod_cashflow_position=Decimal("2"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("-0.1"),
                    quantity=Decimal("1"),
                    epoch=1,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={date(2025, 1, 1): Decimal("1.2")}),
    )
    token = service._encode_page_token(  # pylint: disable=protected-access
        {"valuation_date": "2025-01-01", "security_id": "SEC_A"}
    )
    response = await service.get_position_timeseries(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            reporting_currency="USD",
            include_cash_flows=True,
            page=PageRequest(page_size=10, page_token=token),
            dimensions=["asset_class", "sector", "country"],
        ),
    )
    assert response.rows[0].valuation_status == "restated"
    assert len(response.rows[0].cash_flows) == 3


def test_decode_page_token_invalid_signature() -> None:
    service = make_service()
    token = service._encode_page_token({"valuation_date": "2025-01-01"})  # pylint: disable=protected-access
    service._page_token_secret = "different-secret"  # pylint: disable=protected-access
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._decode_page_token(token)  # pylint: disable=protected-access
    assert exc_info.value.code == "INVALID_REQUEST"


def test_resolve_window_invalid_order() -> None:
    service = make_service()
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._resolve_window(  # pylint: disable=protected-access
            as_of_date=date(2025, 1, 31),
            window=AnalyticsWindow(start_date="2025-02-01", end_date="2025-01-31"),
            period=None,
            inception_date=date(2020, 1, 1),
        )
    assert exc_info.value.code == "INVALID_REQUEST"


def test_resolve_window_unsupported_period() -> None:
    service = make_service()
    with pytest.raises(AnalyticsInputError) as exc_info:
        service._resolve_window(  # pylint: disable=protected-access
            as_of_date=date(2025, 1, 31),
            window=None,
            period="bad_period",
            inception_date=date(2020, 1, 1),
        )
    assert exc_info.value.code == "INVALID_REQUEST"


def test_resolve_window_inception_clamp() -> None:
    service = make_service()
    window = service._resolve_window(  # pylint: disable=protected-access
        as_of_date=date(2025, 1, 31),
        window=None,
        period="five_years",
        inception_date=date(2023, 1, 1),
    )
    assert window.start_date == date(2023, 1, 1)


@pytest.mark.asyncio
async def test_get_portfolio_timeseries_not_found() -> None:
    service = make_service()
    service.repo = SimpleNamespace(get_portfolio=AsyncMock(return_value=None))
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_portfolio_timeseries(
            portfolio_id="UNKNOWN",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_year",
            ),
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_position_timeseries_missing_fx_rate() -> None:
    service = make_service()
    service.repo = SimpleNamespace(
        get_portfolio=AsyncMock(
            return_value=SimpleNamespace(
                portfolio_id="P1",
                base_currency="EUR",
                open_date=date(2020, 1, 1),
                close_date=None,
            )
        ),
        list_position_timeseries_rows=AsyncMock(
            return_value=[
                SimpleNamespace(
                    security_id="SEC_A",
                    valuation_date=date(2025, 1, 1),
                    bod_market_value=Decimal("10"),
                    eod_market_value=Decimal("11"),
                    bod_cashflow_position=Decimal("0"),
                    eod_cashflow_position=Decimal("0"),
                    bod_cashflow_portfolio=Decimal("0"),
                    eod_cashflow_portfolio=Decimal("0"),
                    fees=Decimal("0"),
                    quantity=Decimal("1"),
                    epoch=0,
                    asset_class="Equity",
                    sector="Technology",
                    country="US",
                    position_currency="USD",
                )
            ]
        ),
        get_fx_rates_map=AsyncMock(return_value={}),
    )
    with pytest.raises(AnalyticsInputError) as exc_info:
        await service.get_position_timeseries(
            portfolio_id="P1",
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
                reporting_currency="USD",
            ),
        )
    assert exc_info.value.code == "INSUFFICIENT_DATA"
