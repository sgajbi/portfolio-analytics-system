# src/services/query_service/app/routers/risk.py
from fastapi import APIRouter, status
from ..dtos.risk_dto import RiskRequest
from .legacy_gone import legacy_gone_response, raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Risk Analytics"])


@router.post(
    "/{portfolio_id}/risk",
    status_code=status.HTTP_410_GONE,
    responses={
        status.HTTP_410_GONE: legacy_gone_response(
            capability="risk_analytics",
            target_service="PA",
            target_endpoint="/portfolios/{portfolio_id}/risk",
        )
    },
    summary="[Deprecated] Calculate On-the-Fly Portfolio Risk Analytics",
    description=(
        "Deprecated: advanced risk analytics ownership has moved to PA. "
        "Use PA APIs for authoritative risk calculations."
    ),
    deprecated=True,
)
async def calculate_risk(portfolio_id: str, request: RiskRequest):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="risk_analytics",
        target_service="PA",
        target_endpoint="/portfolios/{portfolio_id}/risk",
    )
