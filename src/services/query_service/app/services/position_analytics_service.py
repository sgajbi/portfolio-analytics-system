# src/services/query_service/app/services/position_analytics_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from decimal import Decimal
from typing import Any
from datetime import date, timedelta

from portfolio_common.db import get_async_db_session
from ..dtos.position_analytics_dto import (
    PositionAnalyticsRequest,
    PositionAnalyticsResponse,
    EnrichedPosition,
    PositionAnalyticsSection,
    MonetaryAmount,
    PositionValuation,
    PositionInstrumentDetails,
    PositionValuationDetail,
)
from ..repositories.position_repository import PositionRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.fx_rate_repository import FxRateRepository
from portfolio_common.monitoring import (
    POSITION_ANALYTICS_DURATION_SECONDS,
    POSITION_ANALYTICS_SECTION_REQUESTED_TOTAL,
)

logger = logging.getLogger(__name__)


class PositionAnalyticsService:
    """
    Orchestrates the data fetching and calculation for position-level analytics.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.position_repo = PositionRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.cashflow_repo = CashflowRepository(db)
        self.fx_repo = FxRateRepository(db)

    async def _enrich_position(
        self,
        portfolio: Any,
        total_market_value_base: Decimal,
        repo_row: Any,
        request: PositionAnalyticsRequest,
    ) -> EnrichedPosition:
        (
            snapshot,
            instrument_name,
            reprocessing_status,
            isin,
            currency,
            asset_class,
            sector,
            country_of_risk,
            epoch,
        ) = repo_row

        market_value_base = snapshot.market_value or Decimal(0)
        position = EnrichedPosition(
            securityId=snapshot.security_id,
            quantity=float(snapshot.quantity),
            weight=float(market_value_base / total_market_value_base)
            if total_market_value_base
            else 0.0,
            held_since_date=snapshot.date,
        )

        enrichment_tasks = {}
        if (
            PositionAnalyticsSection.BASE in request.sections
            or PositionAnalyticsSection.INCOME in request.sections
        ):
            enrichment_tasks["held_since_date"] = self.position_repo.get_held_since_date(
                portfolio.portfolio_id, snapshot.security_id, epoch
            )

        task_results = await asyncio.gather(*enrichment_tasks.values(), return_exceptions=True)
        results_map = dict(zip(enrichment_tasks.keys(), task_results))

        if isinstance(results_map.get("held_since_date"), date):
            position.held_since_date = results_map["held_since_date"]

        income_tasks = {}
        if PositionAnalyticsSection.INCOME in request.sections:
            income_tasks["income_cashflows"] = self.cashflow_repo.get_income_cashflows_for_position(
                portfolio.portfolio_id,
                snapshot.security_id,
                position.held_since_date,
                request.as_of_date,
            )

        income_results = await asyncio.gather(*income_tasks.values())
        income_map = dict(zip(income_tasks.keys(), income_results))

        if "income_cashflows" in income_map:
            cashflows = income_map["income_cashflows"]
            total_income_local = sum(cf.amount for cf in cashflows)

            total_income_base = total_income_local
            if currency != portfolio.base_currency and cashflows:
                min_cf_date = min(cf.cashflow_date for cf in cashflows)
                fx_rates_db = await self.fx_repo.get_fx_rates(
                    currency, portfolio.base_currency, min_cf_date, request.as_of_date
                )
                fx_rates = {r.rate_date: r.rate for r in fx_rates_db}

                # Forward fill missing FX rates without optional pandas dependency.
                filled_fx: dict[date, Decimal] = {}
                last_rate: Decimal | None = None
                current_date = min_cf_date
                while current_date <= request.as_of_date:
                    if current_date in fx_rates:
                        last_rate = fx_rates[current_date]
                    if last_rate is not None:
                        filled_fx[current_date] = last_rate
                    current_date += timedelta(days=1)
                total_income_base = sum(
                    cf.amount * filled_fx.get(cf.cashflow_date, Decimal(1)) for cf in cashflows
                )

            position.income = PositionValuationDetail(
                local=MonetaryAmount(amount=float(total_income_local), currency=currency),
                base=MonetaryAmount(
                    amount=float(total_income_base), currency=portfolio.base_currency
                ),
            )

        if PositionAnalyticsSection.INSTRUMENT_DETAILS in request.sections:
            position.instrument_details = PositionInstrumentDetails(
                name=instrument_name,
                isin=isin,
                assetClass=asset_class,
                sector=sector,
                countryOfRisk=country_of_risk,
                currency=currency,
            )

        if PositionAnalyticsSection.VALUATION in request.sections:
            position.valuation = PositionValuation(
                marketValue=PositionValuationDetail(
                    local=MonetaryAmount(
                        amount=float(snapshot.market_value_local or 0), currency=currency
                    ),
                    base=MonetaryAmount(
                        amount=float(snapshot.market_value or 0), currency=portfolio.base_currency
                    ),
                ),
                costBasis=PositionValuationDetail(
                    local=MonetaryAmount(
                        amount=float(snapshot.cost_basis_local or 0), currency=currency
                    ),
                    base=MonetaryAmount(
                        amount=float(snapshot.cost_basis or 0), currency=portfolio.base_currency
                    ),
                ),
                unrealizedPnl=PositionValuationDetail(
                    local=MonetaryAmount(
                        amount=float(snapshot.unrealized_gain_loss_local or 0), currency=currency
                    ),
                    base=MonetaryAmount(
                        amount=float(snapshot.unrealized_gain_loss or 0),
                        currency=portfolio.base_currency,
                    ),
                ),
            )
        return position

    async def get_position_analytics(
        self, portfolio_id: str, request: PositionAnalyticsRequest
    ) -> PositionAnalyticsResponse:
        with POSITION_ANALYTICS_DURATION_SECONDS.labels(portfolio_id=portfolio_id).time():
            logger.info(
                "Starting position analytics generation for portfolio %s",
                portfolio_id,
                extra={"sections": [s.value for s in request.sections]},
            )
            for section in request.sections:
                POSITION_ANALYTICS_SECTION_REQUESTED_TOTAL.labels(section_name=section.value).inc()

            portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
            if not portfolio:
                raise ValueError(f"Portfolio {portfolio_id} not found")

            repo_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)

            if not repo_results:
                return PositionAnalyticsResponse(
                    portfolio_id=portfolio_id,
                    as_of_date=request.as_of_date,
                    total_market_value=0.0,
                    positions=[],
                )
            total_market_value_base = sum(
                pos.market_value or Decimal(0) for pos, *_ in repo_results
            )
            enrichment_coroutines = [
                self._enrich_position(portfolio, total_market_value_base, row, request)
                for row in repo_results
            ]
            enriched_positions = await asyncio.gather(*enrichment_coroutines)

            logger.info("Successfully generated position analytics for portfolio %s", portfolio_id)
            return PositionAnalyticsResponse(
                portfolio_id=portfolio_id,
                as_of_date=request.as_of_date,
                total_market_value=float(total_market_value_base),
                positions=enriched_positions,
            )


def get_position_analytics_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionAnalyticsService:
    return PositionAnalyticsService(db)
