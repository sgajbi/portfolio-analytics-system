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

logger = logging.getLogger(__name__)

class PositionAnalyticsService:
    """
    Orchestrates the data fetching and calculation for position-level analytics.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.position_repo = PositionRepository(db)
        self.portfolio_repo = PortfolioRepository(db)

    async def get_position_analytics(
        self, portfolio_id: str, request: PositionAnalyticsRequest
    ) -> PositionAnalyticsResponse:
        """
        Fetches and enriches positions with the requested analytics.
        """
        logger.info(f"Generating position analytics for portfolio {portfolio_id}")

        # Fetch portfolio details to get base currency and validate existence
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        # 1. Fetch all base position and instrument data in a single efficient query
        repo_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)

        if not repo_results:
            return PositionAnalyticsResponse(
                portfolio_id=portfolio_id,
                as_of_date=request.as_of_date,
                total_market_value=0.0,
                positions=[]
            )

        # 2. Calculate total portfolio market value for weight calculations
        total_market_value_base = sum(
            pos.market_value or Decimal(0) for pos, *_ in repo_results
        )

        # 3. Concurrently enrich each position
        # (For now, it's synchronous, but the structure is ready for async enrichment)
        enriched_positions: List[EnrichedPosition] = []
        for row in repo_results:
            (
                snapshot, instrument_name, reprocessing_status, isin,
                currency, asset_class, sector, country_of_risk
            ) = row

            market_value_base = snapshot.market_value or Decimal(0)

            # --- BASE Section ---
            position = EnrichedPosition(
                securityId=snapshot.security_id,
                quantity=float(snapshot.quantity),
                weight=float(market_value_base / total_market_value_base) if total_market_value_base else 0.0,
                heldSinceDate=snapshot.date # Placeholder: To be implemented in next PR
            )

            # --- INSTRUMENT_DETAILS Section ---
            if PositionAnalyticsSection.INSTRUMENT_DETAILS in request.sections:
                position.instrument_details = PositionInstrumentDetails(
                    name=instrument_name,
                    isin=isin,
                    assetClass=asset_class,
                    sector=sector,
                    countryOfRisk=country_of_risk,
                    currency=currency
                )

            # --- VALUATION Section ---
            if PositionAnalyticsSection.VALUATION in request.sections:
                position.valuation = PositionValuation(
                    marketValue=MonetaryAmount(
                        amount=float(snapshot.market_value or 0),
                        currency=portfolio.base_currency
                    ),
                    costBasis=MonetaryAmount(
                        amount=float(snapshot.cost_basis or 0),
                        currency=portfolio.base_currency
                    ),
                    unrealizedPnl=MonetaryAmount(
                        amount=float(snapshot.unrealized_gain_loss or 0),
                        currency=portfolio.base_currency
                    )
                )
            
            enriched_positions.append(position)

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