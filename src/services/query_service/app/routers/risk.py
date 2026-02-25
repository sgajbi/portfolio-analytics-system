# src/services/query_service/app/routers/risk.py
from fastapi import APIRouter
from ..dtos.risk_dto import RiskRequest, RiskResponse
from .legacy_gone import raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Risk Analytics"])


@router.post(
    "/{portfolio_id}/risk",
    response_model=RiskResponse,
    response_model_exclude_none=True,
    summary="[Deprecated] Calculate On-the-Fly Portfolio Risk Analytics",
    description=(
        "Deprecated: advanced risk analytics ownership has moved to PA. "
        "Use PA APIs for authoritative risk calculations."
    ),
    deprecated=True,
)
async def calculate_risk(
    portfolio_id: str, request: RiskRequest
):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="risk_analytics",
        target_service="PA",
        target_endpoint="/portfolios/{portfolio_id}/risk",
    )
