# src/services/query_service/app/services/concentration_service.py
import logging
import asyncio
import pandas as pd
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from portfolio_common.db import get_async_db_session
from ..dtos.concentration_dto import (
    ConcentrationRequest, ConcentrationResponse, ResponseSummary,
    BulkConcentration, IssuerConcentration, IssuerExposure
)

from ..repositories.portfolio_repository import PortfolioRepository
from ..repositories.position_repository import PositionRepository
from concentration_analytics_engine.metrics import calculate_bulk_concentration, calculate_issuer_concentration

logger = logging.getLogger(__name__)

class ConcentrationService:
    """
    Orchestrates the data fetching and calculation for concentration analytics.
    """
    def __init__(self, db: AsyncSession):
        self.db = db
        self.portfolio_repo = PortfolioRepository(db)
        self.position_repo = PositionRepository(db)

    async def calculate_concentration(
        self, portfolio_id: str, request: ConcentrationRequest
    ) -> ConcentrationResponse:
        
        portfolio = await self.portfolio_repo.get_by_id(portfolio_id)
        if not portfolio:
            raise ValueError(f"Portfolio {portfolio_id} not found")

        positions_data = await self.position_repo.get_latest_positions_by_portfolio(portfolio_id)
        
        if not positions_data:
            return ConcentrationResponse(
                scope=request.scope,
                summary=ResponseSummary(portfolio_market_value=0.0, findings=[]),
                bulk_concentration=BulkConcentration(
                    top_n_weights={str(n): 0.0 for n in request.options.bulk_top_n},
                    single_position_weight=0.0,
                    hhi=0.0
                ) if "BULK" in request.metrics else None,
                issuer_concentration=IssuerConcentration(top_exposures=[]) if "ISSUER" in request.metrics else None,
            )

        positions_list = [
            {
                "security_id": snapshot.security_id,
                "market_value": snapshot.market_value or Decimal("0"),
                "instrument_name": instrument.name,
                "issuer_id": instrument.issuer_id,
                "ultimate_parent_issuer_id": instrument.ultimate_parent_issuer_id,
                "issuer_name": instrument.name 
            }
            for snapshot, instrument, state in positions_data
        ]
        positions_df = pd.DataFrame(positions_list)
        total_market_value = positions_df["market_value"].sum()

        bulk_concentration_result = None
        issuer_concentration_result = None

        if "BULK" in request.metrics:
            bulk_metrics = calculate_bulk_concentration(
                positions_df, request.options.bulk_top_n
            )
            bulk_concentration_result = BulkConcentration(**bulk_metrics)
        
        if "ISSUER" in request.metrics:
            issuer_metrics = calculate_issuer_concentration(
                positions_df, request.options.issuer_top_n
            )
            issuer_concentration_result = IssuerConcentration(
                top_exposures=[IssuerExposure(**item) for item in issuer_metrics]
            )

        return ConcentrationResponse(
            scope=request.scope,
            summary=ResponseSummary(portfolio_market_value=float(total_market_value), findings=[]),
            bulk_concentration=bulk_concentration_result,
            issuer_concentration=issuer_concentration_result,
        )


def get_concentration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> ConcentrationService:
    """Dependency injector for the ConcentrationService."""
    return ConcentrationService(db)