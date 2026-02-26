# src/services/query_service/app/routers/summary.py
from fastapi import APIRouter
from ..dtos.summary_dto import SummaryRequest, SummaryResponse
from .legacy_gone import raise_legacy_endpoint_gone

router = APIRouter(prefix="/portfolios", tags=["Portfolio Summary"])


@router.post(
    "/{portfolio_id}/summary",
    response_model=SummaryResponse,
    response_model_exclude_none=True,
    deprecated=True,
    summary="Get a Consolidated Portfolio Summary (Deprecated: moved to RAS)",
)
async def get_portfolio_summary(
    portfolio_id: str,
    request: SummaryRequest,
):
    """
    Retrieves a consolidated, dashboard-style summary for a portfolio.

    Deprecated: reporting endpoint ownership has moved to RAS.
    Use `lotus-report` endpoint:
    `POST /reports/portfolios/{portfolio_id}/summary`.

    This endpoint can calculate various sections in a single call:
    - **Wealth**: Total market value and cash balance.
    - **Allocation**: Breakdowns by asset class, sector, currency, etc.
    """
    _ = (portfolio_id, request)
    raise_legacy_endpoint_gone(
        capability="portfolio_summary_report",
        target_service="RAS",
        target_endpoint="/reports/portfolios/{portfolio_id}/summary",
    )
