# src/services/query_service/app/routers/risk.py
from fastapi import APIRouter, status

from ..dtos.risk_dto import RiskRequest
from .legacy_gone import legacy_gone_response, raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Risk Analytics"])


@router.post(
    "/{portfolio_id}/risk",
    include_in_schema=False,
    status_code=status.HTTP_410_GONE,
    responses={
        status.HTTP_410_GONE: legacy_gone_response(
            capability="risk_analytics",
            target_service="lotus-risk",
            target_endpoint="/analytics/risk/calculate",
        )
    },
    summary="[Deprecated] Calculate On-the-Fly Portfolio Risk Analytics",
    description=(
        "Deprecated: advanced risk analytics ownership has moved to lotus-risk. "
        "Use lotus-risk APIs for authoritative risk calculations."
    ),
    deprecated=True,
)
async def calculate_risk(portfolio_id: str, request: RiskRequest):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="risk_analytics",
        target_service="lotus-risk",
        target_endpoint="/analytics/risk/calculate",
    )
