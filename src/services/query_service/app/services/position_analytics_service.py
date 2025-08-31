# src/services/query_service/app/services/position_analytics_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from decimal import Decimal
from typing import Any, List, Dict
import pandas as pd
from datetime import date

from portfolio_common.db import get_async_db_session
from ..dtos.position_analytics_dto import (
    PositionAnalyticsRequest, PositionAnalyticsResponse, EnrichedPosition,
    PositionAnalyticsSection, MonetaryAmount, PositionValuation, PositionInstrumentDetails,
    PositionPerformance
)
from ..repositories.position_repository import PositionRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.performance_repository import PerformanceRepository
from ..repositories.fx_rate_repository import FxRateRepository
from performance_calculator_engine.helpers import resolve_period
from performance_calculator_engine.calculator import PerformanceCalculator
from performance_calculator_engine.constants import FINAL_CUMULATIVE_ROR_PCT

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
        self.perf_repo = PerformanceRepository(db)
        self.fx_repo = FxRateRepository(db)

    async def _calculate_performance(
        self,
        portfolio_id: str,
        security_id: str,
        instrument_currency: str,
        base_currency: str,
        inception_date: date,
        request: PositionAnalyticsRequest
    ) -> Optional[Dict[str, PositionPerformance]]:
        """Calculates TWR for all requested periods for a single position."""
        if not request.performance_options:
            return None

        periods = [
            resolve_period(p, inception_date, request.as_of_date)
            for p in request.performance_options.periods
        ]
        
        min_start = min(p[1] for p in periods)
        
        timeseries_data = await self.perf_repo.get_position_timeseries_for_range(
            portfolio_id, security_id, min_start, request.as_of_date
        )

        if not timeseries_data:
            return {name: PositionPerformance() for name, _, _ in periods}

        # More advanced dual currency logic will go here
        
        return {name: PositionPerformance(localReturn=0.0, baseReturn=0.0) for name, _, _ in periods}


    async def _enrich_position(
        self,
        portfolio: Any,
        total_market_value_base: Decimal,
        repo_row: Any,
        request: PositionAnalyticsRequest
    ) -> EnrichedPosition:
        """Enriches a single position row with requested analytics."""
        (
            snapshot, instrument_name, reprocessing_status, isin,
            currency, asset_class, sector, country_of_risk, epoch
        ) = repo_row

        market_value_base = snapshot.market_value or Decimal(0)

        # --- BASE Section ---
        position = EnrichedPosition(
            securityId=snapshot.security_id,
            quantity=float(snapshot.quantity),
            weight=float(market_value_base / total_market_value_base) if total_market_value_base else 0.0,
            held_since_date=snapshot.date # Default, will be overwritten
        )

        # --- Start Concurrent Enrichment Tasks ---
        enrichment_tasks = {}
        if PositionAnalyticsSection.BASE in request.sections:
            enrichment_tasks['held_since_date'] = self.position_repo.get_held_since_date(
                portfolio.portfolio_id, snapshot.security_id, epoch
            )
        
        if PositionAnalyticsSection.PERFORMANCE in request.sections:
            # Placeholder for inception date logic, for now use portfolio open date
            enrichment_tasks['performance'] = self._calculate_performance(
                portfolio.portfolio_id, snapshot.security_id, currency, portfolio.base_currency,
                portfolio.open_date, request
            )
        
        task_results = await asyncio.gather(*enrichment_tasks.values(), return_exceptions=True)
        results_map = dict(zip(enrichment_tasks.keys(), task_results))
        
        if isinstance(results_map.get('held_since_date'), date):
            position.held_since_date = results_map['held_since_date']
        
        if isinstance(results_map.get('performance'), dict):
            position.performance = results_map['performance']

        # --- Second wave of tasks that depend on the first ---
        income_tasks = {}
        if PositionAnalyticsSection.INCOME in request.sections:
            income_tasks['income'] = self.cashflow_repo.get_total_income_for_position(
                portfolio.portfolio_id, snapshot.security_id, position.held_since_date, request.as_of_date
            )
        
        income_results = await asyncio.gather(*income_tasks.values())
        income_map = dict(zip(income_tasks.keys(), income_results))

        if 'income' in income_map:
            position.income = MonetaryAmount(
                amount=float(income_map['income']),
                currency=portfolio.base_currency # Simplified for now, needs multi-currency logic
            )
        
        # --- Synchronous Section Assembly ---
        if PositionAnalyticsSection.INSTRUMENT_DETAILS in request.sections:
            position.instrument_details = PositionInstrumentDetails(
                name=instrument_name, isin=isin, assetClass=asset_class,
                sector=sector, countryOfRisk=country_of_risk, currency=currency
            )

        if PositionAnalyticsSection.VALUATION in request.sections:
            position.valuation = PositionValuation(
                marketValue=MonetaryAmount(amount=float(snapshot.market_value or 0), currency=portfolio.base_currency),
                costBasis=MonetaryAmount(amount=float(snapshot.cost_basis or 0), currency=portfolio.base_currency),
                unrealizedPnl=MonetaryAmount(amount=float(snapshot.unrealized_gain_loss or 0), currency=portfolio.base_currency)
            )
        
        return position

    async def get_position_analytics(
        self, portfolio_id: str, request: PositionAnalyticsRequest
    ) -> PositionAnalyticsResponse:
        logger.info(f"Generating position analytics for portfolio {portfolio_id}")

        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        repo_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)

        if not repo_results:
            return PositionAnalyticsResponse(
                portfolio_id=portfolio_id, as_of_date=request.as_of_date,
                total_market_value=0.0, positions=[]
            )

        total_market_value_base = sum(pos.market_value or Decimal(0) for pos, *_ in repo_results)

        # Concurrently enrich all positions
        enrichment_coroutines = [
            self._enrich_position(portfolio, total_market_value_base, row, request)
            for row in repo_results
        ]
        enriched_positions = await asyncio.gather(*enrichment_coroutines)

        return PositionAnalyticsResponse(
            portfolio_id=portfolio_id,
            as_of_date=request.as_of_date,
            total_market_value=float(total_market_value_base),
            positions=enriched_positions
        )

def get_position_analytics_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionAnalyticsService:
    """Dependency injector for the PositionAnalyticsService."""
    return PositionAnalyticsService(db)