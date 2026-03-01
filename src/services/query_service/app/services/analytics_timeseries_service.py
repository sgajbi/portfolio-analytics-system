from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.analytics_input_dto import (
    AnalyticsWindow,
    CashFlowObservation,
    LineageMetadata,
    PageMetadata,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsReferenceResponse,
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PortfolioTimeseriesObservation,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
    PositionTimeseriesRow,
    QualityDiagnostics,
)
from ..repositories.analytics_timeseries_repository import AnalyticsTimeseriesRepository


class AnalyticsInputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class AnalyticsTimeseriesService:
    def __init__(self, db: AsyncSession):
        self.repo = AnalyticsTimeseriesRepository(db)
        self._page_token_secret = os.getenv("LOTUS_CORE_PAGE_TOKEN_SECRET", "lotus-core-local-dev")

    def _request_fingerprint(self, payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(serialized.encode("utf-8")).hexdigest()  # nosec B324

    def _encode_page_token(self, payload: dict) -> str:
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(
            self._page_token_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        envelope = {"p": payload, "s": signature}
        return base64.urlsafe_b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")

    def _decode_page_token(self, token: str | None) -> dict:
        if not token:
            return {}
        try:
            decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
            envelope = json.loads(decoded)
            payload = envelope["p"]
            signature = envelope["s"]
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(
                self._page_token_secret.encode("utf-8"),
                serialized.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise AnalyticsInputError("INVALID_REQUEST", "Invalid page token signature.")
            return payload
        except AnalyticsInputError:
            raise
        except Exception as exc:
            raise AnalyticsInputError("INVALID_REQUEST", "Malformed page token.") from exc

    def _resolve_window(
        self,
        *,
        as_of_date: date,
        window: AnalyticsWindow | None,
        period: str | None,
        inception_date: date,
    ) -> AnalyticsWindow:
        if window is not None:
            end_date = min(window.end_date, as_of_date)
            if window.start_date > end_date:
                raise AnalyticsInputError(
                    "INVALID_REQUEST", "window.start_date must be before or equal to end_date."
                )
            return AnalyticsWindow(start_date=window.start_date, end_date=end_date)

        if period == "one_month":
            start = as_of_date - timedelta(days=31)
        elif period == "three_months":
            start = as_of_date - timedelta(days=92)
        elif period == "ytd":
            start = date(as_of_date.year, 1, 1)
        elif period == "one_year":
            start = as_of_date - timedelta(days=365)
        elif period == "three_years":
            start = as_of_date - timedelta(days=365 * 3)
        elif period == "five_years":
            start = as_of_date - timedelta(days=365 * 5)
        elif period == "inception":
            start = inception_date
        else:
            raise AnalyticsInputError("INVALID_REQUEST", "Unsupported period value.")

        if start < inception_date:
            start = inception_date
        return AnalyticsWindow(start_date=start, end_date=as_of_date)

    async def _get_conversion_rates(
        self,
        *,
        portfolio_currency: str,
        reporting_currency: str,
        start_date: date,
        end_date: date,
    ) -> dict[date, Decimal]:
        if portfolio_currency == reporting_currency:
            return {}
        return await self.repo.get_fx_rates_map(
            from_currency=portfolio_currency,
            to_currency=reporting_currency,
            start_date=start_date,
            end_date=end_date,
        )

    @staticmethod
    def _quality_status_from_epoch(epoch: int) -> str:
        if epoch > 0:
            return "restated"
        return "final"

    @staticmethod
    def _cash_flows_from_portfolio_row(row: object) -> list[CashFlowObservation]:
        flows: list[CashFlowObservation] = []
        bod = Decimal(row.bod_cashflow)
        eod = Decimal(row.eod_cashflow)
        fees = Decimal(row.fees)
        if bod != 0:
            flows.append(
                CashFlowObservation(amount=bod, timing="bod", cash_flow_type="external_flow")
            )
        if eod != 0:
            flows.append(
                CashFlowObservation(amount=eod, timing="eod", cash_flow_type="external_flow")
            )
        if fees != 0:
            flows.append(CashFlowObservation(amount=fees, timing="eod", cash_flow_type="fee"))
        return flows

    async def get_portfolio_timeseries(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsTimeseriesRequest,
    ) -> PortfolioAnalyticsTimeseriesResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")

        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = request.reporting_currency or portfolio.base_currency
        fx_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )

        cursor = self._decode_page_token(request.page.page_token)
        cursor_date = (
            date.fromisoformat(cursor["valuation_date"]) if cursor.get("valuation_date") else None
        )
        rows = await self.repo.list_portfolio_timeseries_rows(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            page_size=request.page.page_size,
            cursor_date=cursor_date,
        )

        has_more = len(rows) > request.page.page_size
        rows_page = rows[: request.page.page_size]

        observations: list[PortfolioTimeseriesObservation] = []
        quality_distribution: dict[str, int] = {}
        for row in rows_page:
            valuation_date = row.valuation_date
            conversion_rate = Decimal("1")
            if reporting_currency != portfolio.base_currency:
                if valuation_date not in fx_rates:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        f"Missing FX rate for {portfolio.base_currency}/{reporting_currency} on {valuation_date}.",
                    )
                conversion_rate = fx_rates[valuation_date]
            quality = self._quality_status_from_epoch(int(row.epoch))
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1

            observations.append(
                PortfolioTimeseriesObservation(
                    valuation_date=valuation_date,
                    beginning_market_value=Decimal(row.bod_market_value) * conversion_rate,
                    ending_market_value=Decimal(row.eod_market_value) * conversion_rate,
                    valuation_status=quality,
                    cash_flows=[
                        CashFlowObservation(
                            amount=flow.amount * conversion_rate,
                            timing=flow.timing,
                            cash_flow_type=flow.cash_flow_type,
                        )
                        for flow in self._cash_flows_from_portfolio_row(row)
                    ],
                )
            )

        next_page_token: str | None = None
        if has_more and rows_page:
            next_page_token = self._encode_page_token(
                {"valuation_date": rows_page[-1].valuation_date.isoformat()}
            )

        latest_date = await self.repo.get_latest_portfolio_timeseries_date(portfolio_id)
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        return PortfolioAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            portfolio_open_date=portfolio.open_date,
            portfolio_close_date=portfolio.close_date,
            performance_end_date=latest_date,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=QualityDiagnostics(
                quality_status_distribution=quality_distribution,
                missing_dates_count=0,
                stale_points_count=0,
            ),
            page=PageMetadata(next_page_token=next_page_token),
            observations=observations,
        )

    async def get_position_timeseries(
        self,
        *,
        portfolio_id: str,
        request: PositionAnalyticsTimeseriesRequest,
    ) -> PositionAnalyticsTimeseriesResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        resolved_window = self._resolve_window(
            as_of_date=request.as_of_date,
            window=request.window,
            period=request.period,
            inception_date=portfolio.open_date,
        )
        reporting_currency = request.reporting_currency or portfolio.base_currency
        fx_rates = await self._get_conversion_rates(
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
        )

        cursor = self._decode_page_token(request.page.page_token)
        cursor_date = (
            date.fromisoformat(cursor["valuation_date"]) if cursor.get("valuation_date") else None
        )
        cursor_security_id = cursor.get("security_id")
        dimension_filters = {
            item.dimension: set(item.values) for item in request.filters.dimension_filters
        }
        rows = await self.repo.list_position_timeseries_rows(
            portfolio_id=portfolio_id,
            start_date=resolved_window.start_date,
            end_date=resolved_window.end_date,
            page_size=request.page.page_size,
            cursor_date=cursor_date,
            cursor_security_id=cursor_security_id,
            security_ids=request.filters.security_ids,
            position_ids=request.filters.position_ids,
            dimension_filters=dimension_filters,
        )

        has_more = len(rows) > request.page.page_size
        rows_page = rows[: request.page.page_size]

        quality_distribution: dict[str, int] = {}
        response_rows: list[PositionTimeseriesRow] = []
        for row in rows_page:
            quality = self._quality_status_from_epoch(int(row.epoch))
            quality_distribution[quality] = quality_distribution.get(quality, 0) + 1
            conversion_rate: Decimal | None = None
            if reporting_currency != portfolio.base_currency:
                if row.valuation_date not in fx_rates:
                    raise AnalyticsInputError(
                        "INSUFFICIENT_DATA",
                        f"Missing FX rate for {portfolio.base_currency}/{reporting_currency} on {row.valuation_date}.",
                    )
                conversion_rate = fx_rates[row.valuation_date]

            position_id = f"{portfolio_id}:{row.security_id}"
            dimensions = {dim: getattr(row, dim, None) for dim in request.dimensions}
            cash_flows: list[CashFlowObservation] = []
            if request.include_cash_flows:
                bod = Decimal(row.bod_cashflow_position)
                eod = Decimal(row.eod_cashflow_position)
                fees = Decimal(row.fees)
                if bod != 0:
                    cash_flows.append(
                        CashFlowObservation(
                            amount=bod,
                            timing="bod",
                            cash_flow_type="external_flow",
                        )
                    )
                if eod != 0:
                    cash_flows.append(
                        CashFlowObservation(
                            amount=eod,
                            timing="eod",
                            cash_flow_type="external_flow",
                        )
                    )
                if fees != 0:
                    cash_flows.append(
                        CashFlowObservation(amount=fees, timing="eod", cash_flow_type="fee")
                    )

            response_rows.append(
                PositionTimeseriesRow(
                    position_id=position_id,
                    security_id=row.security_id,
                    valuation_date=row.valuation_date,
                    dimensions=dimensions,
                    beginning_market_value_position_currency=Decimal(row.bod_market_value),
                    ending_market_value_position_currency=Decimal(row.eod_market_value),
                    beginning_market_value_portfolio_currency=Decimal(row.bod_market_value),
                    ending_market_value_portfolio_currency=Decimal(row.eod_market_value),
                    beginning_market_value_reporting_currency=(
                        Decimal(row.bod_market_value) * conversion_rate
                        if conversion_rate is not None
                        else None
                    ),
                    ending_market_value_reporting_currency=(
                        Decimal(row.eod_market_value) * conversion_rate
                        if conversion_rate is not None
                        else None
                    ),
                    valuation_status=quality,
                    quantity=Decimal(row.quantity),
                    cash_flows=cash_flows,
                )
            )

        next_page_token: str | None = None
        if has_more and rows_page:
            last = rows_page[-1]
            next_page_token = self._encode_page_token(
                {"valuation_date": last.valuation_date.isoformat(), "security_id": last.security_id}
            )

        fingerprint = self._request_fingerprint(
            {
                "endpoint": "position-timeseries",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        return PositionAnalyticsTimeseriesResponse(
            portfolio_id=portfolio_id,
            portfolio_currency=portfolio.base_currency,
            reporting_currency=reporting_currency,
            resolved_window=resolved_window,
            frequency=request.frequency,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
            diagnostics=QualityDiagnostics(
                quality_status_distribution=quality_distribution,
                missing_dates_count=0,
                stale_points_count=0,
            ),
            page=PageMetadata(next_page_token=next_page_token),
            rows=response_rows,
        )

    async def get_portfolio_reference(
        self,
        *,
        portfolio_id: str,
        request: PortfolioAnalyticsReferenceRequest,
    ) -> PortfolioAnalyticsReferenceResponse:
        portfolio = await self.repo.get_portfolio(portfolio_id)
        if portfolio is None:
            raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Portfolio not found.")
        latest_date = await self.repo.get_latest_portfolio_timeseries_date(portfolio_id)
        fingerprint = self._request_fingerprint(
            {
                "endpoint": "portfolio-reference",
                "portfolio_id": portfolio_id,
                "request": request.model_dump(mode="json"),
            }
        )
        return PortfolioAnalyticsReferenceResponse(
            portfolio_id=portfolio.portfolio_id,
            portfolio_currency=portfolio.base_currency,
            portfolio_open_date=portfolio.open_date,
            portfolio_close_date=portfolio.close_date,
            performance_end_date=latest_date,
            client_id=portfolio.client_id,
            booking_center_code=portfolio.booking_center_code,
            portfolio_type=portfolio.portfolio_type,
            objective=portfolio.objective,
            lineage=LineageMetadata(
                generated_by="integration.analytics_inputs",
                generated_at=datetime.now(UTC),
                request_fingerprint=fingerprint,
                data_version="state_inputs_v1",
            ),
        )
