# src/services/query_service/app/routers/performance.py
from fastapi import APIRouter, status

from ..dtos.mwr_dto import MWRRequest
from ..dtos.performance_dto import PerformanceRequest
from .legacy_gone import legacy_gone_response, raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Performance"])


@router.post(
    "/{portfolio_id}/performance",
    status_code=status.HTTP_410_GONE,
    responses={
        status.HTTP_410_GONE: legacy_gone_response(
            capability="performance_twr",
            target_service="lotus-performance",
            target_endpoint="/portfolios/{portfolio_id}/performance",
        )
    },
    summary="[Deprecated] Calculate On-the-Fly Portfolio Performance (TWR)",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to lotus-performance. "
        "Use lotus-performance APIs for authoritative performance calculations."
    ),
    deprecated=True,
)
async def calculate_performance(portfolio_id: str, request: PerformanceRequest):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="performance_twr",
        target_service="lotus-performance",
        target_endpoint="/portfolios/{portfolio_id}/performance",
    )


@router.post(
    "/{portfolio_id}/performance/mwr",
    status_code=status.HTTP_410_GONE,
    responses={
        status.HTTP_410_GONE: legacy_gone_response(
            capability="performance_mwr",
            target_service="lotus-performance",
            target_endpoint="/portfolios/{portfolio_id}/performance/mwr",
        )
    },
    summary="[Deprecated] Calculate Money-Weighted Return (MWR / IRR) for a Portfolio",
    description=(
        "Deprecated: advanced performance analytics ownership has moved to lotus-performance. "
        "Use lotus-performance APIs for authoritative MWR calculations."
    ),
    deprecated=True,
)
async def calculate_mwr(portfolio_id: str, request: MWRRequest):
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="performance_mwr",
        target_service="lotus-performance",
        target_endpoint="/portfolios/{portfolio_id}/performance/mwr",
    )
