# src/services/query_service/app/routers/concentration.py
from fastapi import APIRouter, status

from ..dtos.concentration_dto import ConcentrationRequest
from .legacy_gone import legacy_gone_response, raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Concentration Analytics"])


@router.post(
    "/{portfolio_id}/concentration",
    include_in_schema=False,
    status_code=status.HTTP_410_GONE,
    responses={
        status.HTTP_410_GONE: legacy_gone_response(
            capability="concentration_analytics",
            target_service="lotus-risk",
            target_endpoint="/analytics/risk/concentration",
        )
    },
    summary="[Deprecated] Calculate On-the-Fly Portfolio Concentration Analytics",
    description=(
        "Deprecated: concentration analytics ownership has moved to lotus-risk. "
        "Use lotus-risk analytics contracts for concentration metrics."
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
        target_service="lotus-risk",
        target_endpoint="/analytics/risk/concentration",
    )
