# src/services/query_service/app/routers/concentration.py
from fastapi import APIRouter
from ..dtos.concentration_dto import ConcentrationRequest, ConcentrationResponse
from .legacy_gone import raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Concentration Analytics"])


@router.post(
    "/{portfolio_id}/concentration",
    response_model=ConcentrationResponse,
    summary="[Deprecated] Calculate On-the-Fly Portfolio Concentration Analytics",
    description=(
        "Deprecated: concentration analytics ownership has moved to PA. "
        "Use PA analytics contracts for concentration metrics."
    ),
    deprecated=True,
)
async def calculate_concentration(
    portfolio_id: str,
    request: ConcentrationRequest,
):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="concentration_analytics",
        target_service="PA",
        target_endpoint="/portfolios/{portfolio_id}/concentration",
    )
