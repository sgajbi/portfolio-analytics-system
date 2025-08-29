# src/services/query_service/app/routers/risk.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session
from ..dtos.risk_dto import RiskRequest, RiskResponse
from ..services.risk_service import RiskService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/portfolios",
    tags=["Risk Analytics"]
)

def get_risk_service(db: AsyncSession = Depends(get_async_db_session)) -> RiskService:
    """Dependency injector for the RiskService."""
    return RiskService(db)

@router.post(
    "/{portfolio_id}/risk",
    response_model=RiskResponse,
    response_model_exclude_none=True,
    summary="Calculate On-the-Fly Portfolio Risk Analytics",
    description="Calculates a set of portfolio risk metrics (e.g., Volatility, Sharpe, VaR) for one or more specified periods."
)
async def calculate_risk(
    portfolio_id: str,
    request: RiskRequest,
    risk_service: RiskService = Depends(get_risk_service)
):
    """
    Calculates portfolio risk metrics based on a flexible request.

    - **portfolio_id**: The unique identifier for the portfolio.
    - **Request Body**: A JSON object specifying the scope, periods, metrics, and options for the calculation.
    """
    try:
        return await risk_service.calculate_risk(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during risk calculation for portfolio %s.",
            portfolio_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred during risk calculation."
        )