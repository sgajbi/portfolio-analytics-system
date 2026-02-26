import logging
import os

import httpx
import pandas as pd
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import DAILY_ROR_PCT, DATE
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
        self.base_url = os.getenv("LOTUS_RISK_BASE_URL", "http://localhost:8130").rstrip("/")
        self.timeout_seconds = int(os.getenv("LOTUS_RISK_TIMEOUT_SECONDS", "10"))

    @staticmethod
    def _convert_timeseries_to_dict(timeseries_data: list) -> list[dict]:
        return [
            {
                "date": r.date.isoformat(),
                "bod_market_value": r.bod_market_value,
                "eod_market_value": r.eod_market_value,
                "bod_cashflow": r.bod_cashflow,
                "eod_cashflow": r.eod_cashflow,
                "fees": r.fees,
            }
            for r in timeseries_data
        ]

    async def _build_returns_series(self, portfolio_id: str, request: RiskRequest) -> list[dict]:
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        resolved_periods = [
            resolve_period(
                period_type=p.type,
                name=p.name or p.type,
                from_date=getattr(p, "from_date", None),
                to_date=getattr(p, "to_date", None),
                year=getattr(p, "year", None),
                inception_date=portfolio.open_date,
                as_of_date=request.scope.as_of_date,
            )
            for p in request.periods
        ]
        if not resolved_periods:
            return []

        min_start = min(p[1] for p in resolved_periods)
        max_end = max(p[2] for p in resolved_periods)

        timeseries_data = await self.perf_repo.get_portfolio_timeseries_for_range(
            portfolio_id, min_start, max_end
        )
        if not timeseries_data:
            return []

        timeseries_dicts = self._convert_timeseries_to_dict(timeseries_data)
        calculator = PerformanceCalculator(
            config={
                "metric_basis": request.scope.net_or_gross,
                "period_type": "EXPLICIT",
                "performance_start_date": portfolio.open_date.isoformat(),
                "report_start_date": min_start.isoformat(),
                "report_end_date": max_end.isoformat(),
            }
        )
        returns_df = calculator.calculate_performance(timeseries_dicts)
        if returns_df.empty:
            return []

        returns_df[DATE] = pd.to_datetime(returns_df[DATE])
        return [
            {
                "date": row[DATE].date().isoformat(),
                "value": (
                    row[DAILY_ROR_PCT].item()
                    if hasattr(row[DAILY_ROR_PCT], "item")
                    else row[DAILY_ROR_PCT]
                ),
            }
            for _, row in returns_df[[DATE, DAILY_ROR_PCT]].dropna().iterrows()
        ]

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

        endpoint = f"{self.base_url}/analytics/risk/calculate"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)

        if response.status_code >= 400:
            detail = response.text
            logger.error("lotus-risk request failed: %s %s", response.status_code, detail)
            raise RuntimeError(
                f"lotus-risk request failed with status {response.status_code}: {detail}"
            )

        return RiskResponse.model_validate(response.json())
