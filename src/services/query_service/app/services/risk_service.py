import logging
import os
from datetime import date
from typing import Any

import httpx
from performance_calculator_engine.helpers import resolve_period
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.risk_dto import RiskRequest, RiskResponse
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)


class RiskService:
    """Adapter that sources risk analytics from lotus-risk service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.perf_repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.risk_base_url = os.getenv("LOTUS_RISK_BASE_URL", "http://localhost:8130").rstrip("/")
        self.performance_base_url = os.getenv(
            "LOTUS_PERFORMANCE_BASE_URL", "http://localhost:8000"
        ).rstrip("/")
        self.timeout_seconds = int(os.getenv("LOTUS_RISK_TIMEOUT_SECONDS", "10"))

    @staticmethod
    def _period_to_pa_type(period_type: str) -> str:
        mapping = {
            "MTD": "MTD",
            "QTD": "QTD",
            "YTD": "YTD",
            "THREE_YEAR": "3Y",
            "FIVE_YEAR": "5Y",
            "SI": "ITD",
            "EXPLICIT": "EXPLICIT",
            "YEAR": "EXPLICIT",
        }
        if period_type not in mapping:
            raise ValueError(
                f"Unsupported period type for lotus-performance mapping: {period_type}"
            )
        return mapping[period_type]

    @staticmethod
    def _convert_timeseries_to_valuation_points(timeseries_data: list[Any]) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for index, row in enumerate(timeseries_data, start=1):
            points.append(
                {
                    "day": index,
                    "perf_date": row.date.isoformat(),
                    "begin_mv": float(row.bod_market_value or 0),
                    "bod_cf": float(row.bod_cashflow or 0),
                    "eod_cf": float(row.eod_cashflow or 0),
                    "mgmt_fees": float(row.fees or 0),
                    "end_mv": float(row.eod_market_value or 0),
                }
            )
        return points

    async def _build_returns_series(
        self, portfolio_id: str, request: RiskRequest
    ) -> list[dict[str, Any]]:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        resolved_periods = []
        for period in request.periods:
            from_date = getattr(period, "from_date", None)
            to_date = getattr(period, "to_date", None)
            year = getattr(period, "year", None)
            if period.type == "YEAR" and year is not None:
                from_date = date(year, 1, 1)
                to_date = date(year, 12, 31)

            resolved_periods.append(
                resolve_period(
                    period_type=period.type,
                    name=period.name or period.type,
                    from_date=from_date,
                    to_date=to_date,
                    year=year,
                    inception_date=portfolio.open_date,
                    as_of_date=request.scope.as_of_date,
                )
            )

        if not resolved_periods:
            return []

        min_start = min(p[1] for p in resolved_periods)
        max_end = max(p[2] for p in resolved_periods)

        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start, max_end
        )
        if not timeseries_data:
            return []

        valuation_points = self._convert_timeseries_to_valuation_points(timeseries_data)
        payload = {
            "portfolio_id": portfolio_id,
            "performance_start_date": portfolio.open_date.isoformat(),
            "metric_basis": request.scope.net_or_gross,
            "report_start_date": min_start.isoformat(),
            "report_end_date": max_end.isoformat(),
            "analyses": [{"period": "EXPLICIT", "frequencies": ["daily"]}],
            "valuation_points": valuation_points,
            "currency": request.scope.reporting_currency or portfolio.base_currency,
            "output": {"include_cumulative": True, "include_timeseries": True},
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.performance_base_url}/performance/twr", json=payload
            )

        if response.status_code >= 400:
            detail = response.text
            raise RuntimeError(
                f"lotus-performance request failed with status {response.status_code}: {detail}"
            )

        body = response.json()
        period_payload = next(iter((body.get("results_by_period") or {}).values()), None)
        if period_payload is None:
            return []

        daily_items = (period_payload.get("breakdowns") or {}).get("daily") or []
        returns: list[dict[str, Any]] = []
        for item in daily_items:
            period_value = item.get("period")
            summary = item.get("summary") or {}
            daily_return = summary.get("period_return_pct")
            if period_value is None or daily_return is None:
                continue
            returns.append({"date": str(period_value)[:10], "value": daily_return})

        return returns

    async def calculate_risk(self, portfolio_id: str, request: RiskRequest) -> RiskResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        returns = await self._build_returns_series(portfolio_id, request)
        if not returns:
            return RiskResponse(scope=request.scope, results={})

        payload = request.model_dump()
        payload["portfolioOpenDate"] = portfolio.open_date.isoformat()
        payload["returns"] = returns
        payload["benchmarkReturns"] = []

        endpoint = f"{self.risk_base_url}/analytics/risk/calculate"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)

        if response.status_code >= 400:
            detail = response.text
            logger.error("lotus-risk request failed: %s %s", response.status_code, detail)
            raise RuntimeError(
                f"lotus-risk request failed with status {response.status_code}: {detail}"
            )

        return RiskResponse.model_validate(response.json())
