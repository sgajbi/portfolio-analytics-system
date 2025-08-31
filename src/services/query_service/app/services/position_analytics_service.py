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

logger = logging.getLogger(__name__)

class PositionAnalyticsService:
    """
    Orchestrates the data fetching and calculation for position-level analytics.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.position_repo = PositionRepository(db)

    async def get_position_analytics(
        self, portfolio_id: str, request: PositionAnalyticsRequest
    ) -> PositionAnalyticsResponse:
        """
        Fetches and enriches positions with the requested analytics.
        """
        logger.info(f"Generating position analytics for portfolio {portfolio_id}")

        # 1. Fetch all base position and instrument data in a single efficient query
        repo_results = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)

        if not repo_results:
            return PositionAnalyticsResponse(
                portfolioId=portfolio_id,
                asOfDate=request.as_of_date,
                totalMarketValue=0.0,
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
                        currency=portfolio_id # Placeholder for portfolio base currency
                    ),
                    costBasis=MonetaryAmount(
                        amount=float(snapshot.cost_basis or 0),
                        currency=portfolio_id # Placeholder
                    ),
                    unrealizedPnl=MonetaryAmount(
                        amount=float(snapshot.unrealized_gain_loss or 0),
                        currency=portfolio_id # Placeholder
                    )
                )
            
            enriched_positions.append(position)

        return PositionAnalyticsResponse(
            portfolioId=portfolio_id,
            asOfDate=request.as_of_date,
            totalMarketValue=float(total_market_value_base),
            positions=enriched_positions
        )


def get_position_analytics_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> PositionAnalyticsService:
    """Dependency injector for the PositionAnalyticsService."""
    return PositionAnalyticsService(db)