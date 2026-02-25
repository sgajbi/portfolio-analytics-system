# src/services/query_service/app/routers/performance.py
from fastapi import APIRouter
from ..dtos.performance_dto import PerformanceRequest, PerformanceResponse
from ..dtos.mwr_dto import MWRRequest, MWRResponse
from .legacy_gone import raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Performance"])


@router.post(
    "/{portfolio_id}/performance",
    response_model=PerformanceResponse,
    response_model_exclude_none=True,
    summary="[Deprecated] Calculate On-the-Fly Portfolio Performance (TWR)",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to PA. "
        "Use PA APIs for authoritative performance calculations."
    ),
    deprecated=True,
)
async def calculate_performance(
    portfolio_id: str, request: PerformanceRequest
):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="performance_twr",
        target_service="PA",
        target_endpoint="/portfolios/{portfolio_id}/performance",
    )


@router.post(
    "/{portfolio_id}/performance/mwr",
    response_model=MWRResponse,
    summary="[Deprecated] Calculate Money-Weighted Return (MWR / IRR) for a Portfolio",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to PA. "
        "Use PA APIs for authoritative MWR calculations."
    ),
    deprecated=True,
)
async def calculate_mwr(
    portfolio_id: str, request: MWRRequest
):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="performance_mwr",
        target_service="PA",
        target_endpoint="/portfolios/{portfolio_id}/performance/mwr",
    )
