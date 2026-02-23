# src/services/query_service/app/routers/concentration.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status

from ..dtos.concentration_dto import ConcentrationRequest, ConcentrationResponse
from ..services.concentration_service import ConcentrationService, get_concentration_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolios", tags=["Concentration Analytics"])


@router.post(
    "/{portfolio_id}/concentration",
    response_model=ConcentrationResponse,
    summary="Calculate On-the-Fly Portfolio Concentration Analytics",
)
async def calculate_concentration(
    portfolio_id: str,
    request: ConcentrationRequest,
    service: ConcentrationService = Depends(get_concentration_service),
):
    """
    Calculates a set of portfolio concentration metrics (e.g., Issuer, Bulk)
    for a given portfolio as of a specific date.
    """
    try:
        return await service.calculate_concentration(portfolio_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception:
        logger.exception(
            "An unexpected error occurred during concentration calculation for portfolio %s.",
            portfolio_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected server error occurred during concentration calculation.",
        )
