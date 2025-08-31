# src/services/query_service/app/services/position_analytics_service.py
import logging
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from decimal import Decimal

from portfolio_common.db import get_async_db_session
from ..dtos.position_analytics_dto import (
    PositionAnalyticsRequest, PositionAnalyticsResponse, EnrichedPosition,
    PositionAnalyticsSection, MonetaryAmount, PositionValuation, PositionInstrumentDetails
)
from ..repositories.position_repository import PositionRepository
from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.cashflow_repository import CashflowRepository

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

    async def _enrich_position(
        self,
        portfolio_id: str,
        base_currency: str,
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
            heldSinceDate=snapshot.date # Default, will be overwritten
        )

        # --- Start Concurrent Enrichment Tasks ---
        enrichment_tasks = {}
        if PositionAnalyticsSection.INCOME in request.sections or PositionAnalyticsSection.BASE in request.sections:
            # heldSinceDate is needed for both BASE and INCOME
            enrichment_tasks['held_since_date'] = self.position_repo.get_held_since_date(
                portfolio_id, snapshot.security_id, epoch
            )
        
        task_results = await asyncio.gather(*enrichment_tasks.values())
        results_map = dict(zip(enrichment_tasks.keys(), task_results))
        
        held_since_date = results_map.get('held_since_date', snapshot.date)
        position.heldSinceDate = held_since_date

        # --- Second wave of tasks that depend on the first ---
        income_tasks = {}
        if PositionAnalyticsSection.INCOME in request.sections:
            income_tasks['income'] = self.cashflow_repo.get_total_income_for_position(
                portfolio_id, snapshot.security_id, held_since_date, request.as_of_date
            )
        
        income_results = await asyncio.gather(*income_tasks.values())
        income_map = dict(zip(income_tasks.keys(), income_results))

        if 'income' in income_map:
            position.income = MonetaryAmount(
                amount=float(income_map['income']),
                currency=base_currency # Simplified for now, needs multi-currency logic
            )
        
        # --- Synchronous Section Assembly ---
        if PositionAnalyticsSection.INSTRUMENT_DETAILS in request.sections:
            position.instrument_details = PositionInstrumentDetails(
                name=instrument_name, isin=isin, assetClass=asset_class,
                sector=sector, countryOfRisk=country_of_risk, currency=currency
            )

        if PositionAnalyticsSection.VALUATION in request.sections:
            position.valuation = PositionValuation(
                marketValue=MonetaryAmount(amount=float(snapshot.market_value or 0), currency=base_currency),
                costBasis=MonetaryAmount(amount=float(snapshot.cost_basis or 0), currency=base_currency),
                unrealizedPnl=MonetaryAmount(amount=float(snapshot.unrealized_gain_loss or 0), currency=base_currency)
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
            self._enrich_position(portfolio_id, portfolio.base_currency, total_market_value_base, row, request)
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