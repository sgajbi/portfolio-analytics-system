import logging
import os
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from performance_calculator_engine.helpers import resolve_period
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.performance_dto import (
    PerformanceAttributes,
    PerformanceBreakdown,
    PerformanceRequest,
    PerformanceResponse,
    PerformanceResult,
)
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)


class PerformanceService:
    """Adapter that sources performance analytics from lotus-performance service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PerformanceRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.base_url = os.getenv("LOTUS_PERFORMANCE_BASE_URL", "http://localhost:8000").rstrip("/")
        self.timeout_seconds = int(os.getenv("LOTUS_PERFORMANCE_TIMEOUT_SECONDS", "15"))

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
    def _breakdown_to_pa_frequencies(breakdown: str | None) -> list[str]:
        if not breakdown:
            return ["monthly"]
        mapping = {
            "DAILY": "daily",
            "WEEKLY": "weekly",
            "MONTHLY": "monthly",
            "QUARTERLY": "quarterly",
        }
        return [mapping.get(breakdown, "monthly")]

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

    @staticmethod
    def _aggregate_attributes_from_timeseries(timeseries_slice: list[Any]) -> PerformanceAttributes:
        if not timeseries_slice:
            return PerformanceAttributes()
        return PerformanceAttributes(
            begin_market_value=timeseries_slice[0].bod_market_value,
            end_market_value=timeseries_slice[-1].eod_market_value,
            total_cashflow=sum(
                (r.bod_cashflow or Decimal(0)) + (r.eod_cashflow or Decimal(0))
                for r in timeseries_slice
            ),
            bod_cashflow=sum((r.bod_cashflow or Decimal(0)) for r in timeseries_slice),
            eod_cashflow=sum((r.eod_cashflow or Decimal(0)) for r in timeseries_slice),
            fees=sum((r.fees or Decimal(0)) for r in timeseries_slice),
        )

    @staticmethod
    def _extract_annualized(period_payload: dict[str, Any]) -> float | None:
        breakdowns = period_payload.get("breakdowns") or {}
        for _, items in breakdowns.items():
            if items:
                summary = items[-1].get("summary") or {}
                annualized = summary.get("annualized_return_pct")
                if annualized is not None:
                    return float(annualized)
        return None

    @staticmethod
    def _extract_breakdown_results(
        period_payload: dict[str, Any],
        breakdown: str,
        default_start: date,
        default_end: date,
    ) -> list[PerformanceResult]:
        key_map = {
            "DAILY": "daily",
            "WEEKLY": "weekly",
            "MONTHLY": "monthly",
            "QUARTERLY": "quarterly",
        }
        freq_key = key_map.get(breakdown)
        if not freq_key:
            return []

        items = (period_payload.get("breakdowns") or {}).get(freq_key) or []
        results: list[PerformanceResult] = []
        for item in items:
            summary = item.get("summary") or {}
            raw_period = item.get("period")
            item_date = default_end
            if isinstance(raw_period, str):
                try:
                    item_date = date.fromisoformat(raw_period[:10])
                except ValueError:
                    item_date = default_end

            payload: dict[str, Any] = {
                "start_date": item_date,
                "end_date": item_date,
                "cumulative_return": summary.get("period_return_pct"),
                "annualized_return": summary.get("annualized_return_pct"),
            }
            value = summary.get("period_return_pct")
            if breakdown == "DAILY":
                payload["dailyReturn"] = value
            elif breakdown == "WEEKLY":
                payload["weeklyReturn"] = value
            elif breakdown == "MONTHLY":
                payload["monthlyReturn"] = value
            elif breakdown == "QUARTERLY":
                payload["quarterlyReturn"] = value

            results.append(PerformanceResult.model_validate(payload))

        if not results and items:
            results.append(PerformanceResult(start_date=default_start, end_date=default_end))
        return results

    async def calculate_performance(
        self, portfolio_id: str, request: PerformanceRequest
    ) -> PerformanceResponse:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found.")

        resolved_periods: list[tuple[str, date, date, Any]] = []
        for period in request.periods:
            from_date = getattr(period, "from_date", None)
            to_date = getattr(period, "to_date", None)
            year = getattr(period, "year", None)
            if period.type == "YEAR" and year is not None:
                from_date = date(year, 1, 1)
                to_date = date(year, 12, 31)
            resolved = resolve_period(
                period_type=period.type,
                name=period.name or period.type,
                from_date=from_date,
                to_date=to_date,
                year=year,
                inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date,
            )
            resolved_periods.append((resolved[0], resolved[1], resolved[2], period))

        if not resolved_periods:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        min_date = min(p[1] for p in resolved_periods)
        max_date = max(p[2] for p in resolved_periods)
        timeseries_data = await self.repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_date, max_date
        )
        if not timeseries_data:
            return PerformanceResponse(scope=request.scope, summary={}, breakdowns=None)

        valuation_points = self._convert_timeseries_to_valuation_points(timeseries_data)
        summary: dict[str, PerformanceResult] = {}
        breakdowns: dict[str, PerformanceBreakdown] = {}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for period_name, start_date, end_date, period in resolved_periods:
                analyses = [
                    {
                        "period": self._period_to_pa_type(period.type),
                        "frequencies": self._breakdown_to_pa_frequencies(period.breakdown),
                    }
                ]

                payload: dict[str, Any] = {
                    "portfolio_id": portfolio_id,
                    "performance_start_date": portfolio.open_date.isoformat(),
                    "metric_basis": request.scope.net_or_gross,
                    "report_end_date": end_date.isoformat(),
                    "analyses": analyses,
                    "valuation_points": valuation_points,
                    "currency": request.scope.reporting_currency or portfolio.base_currency,
                    "output": {
                        "include_cumulative": request.options.include_cumulative,
                        "include_timeseries": bool(period.breakdown),
                    },
                }
                if self._period_to_pa_type(period.type) == "EXPLICIT":
                    payload["report_start_date"] = start_date.isoformat()

                response = await client.post(f"{self.base_url}/performance/twr", json=payload)
                if response.status_code >= 400:
                    detail = response.text
                    raise RuntimeError(
                        "lotus-performance request failed with status "
                        f"{response.status_code}: {detail}"
                    )

                body = response.json()
                period_payload = next(iter((body.get("results_by_period") or {}).values()), None)
                if period_payload is None:
                    summary[period_name] = PerformanceResult(
                        start_date=start_date, end_date=end_date
                    )
                    continue

                portfolio_return = period_payload.get("portfolio_return") or {}
                annualized = self._extract_annualized(period_payload)
                period_timeseries = [
                    row for row in timeseries_data if start_date <= row.date <= end_date
                ]

                summary[period_name] = PerformanceResult(
                    start_date=start_date,
                    end_date=end_date,
                    cumulative_return=(
                        float(portfolio_return.get("base"))
                        if request.options.include_cumulative
                        and portfolio_return.get("base") is not None
                        else None
                    ),
                    annualized_return=(annualized if request.options.include_annualized else None),
                    attributes=(
                        self._aggregate_attributes_from_timeseries(period_timeseries)
                        if request.options.include_attributes
                        else None
                    ),
                )

                if period.breakdown:
                    breakdown_items = self._extract_breakdown_results(
                        period_payload=period_payload,
                        breakdown=period.breakdown,
                        default_start=start_date,
                        default_end=end_date,
                    )
                    breakdowns[period_name] = PerformanceBreakdown(
                        breakdown_type=period.breakdown,
                        results=breakdown_items,
                    )

        return PerformanceResponse(
            scope=request.scope, summary=summary, breakdowns=breakdowns or None
        )
