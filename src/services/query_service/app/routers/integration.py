from typing import cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.db import get_async_db_session

from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse
from ..services.integration_service import IntegrationService

router = APIRouter(prefix="/integration", tags=["Integration Contracts"])


def get_integration_service(
    db: AsyncSession = Depends(get_async_db_session),
) -> IntegrationService:
    return IntegrationService(db)


@router.get(
    "/policy/effective",
    response_model=EffectiveIntegrationPolicyResponse,
    response_model_by_alias=True,
    summary="Get effective lotus-core integration policy",
    description=(
        "Returns effective policy diagnostics and provenance for the given consumer and tenant "
        "context, including strict-mode behavior and allowed sections."
    ),
)
async def get_effective_integration_policy(
    consumer_system: str = Query("lotus-gateway", alias="consumerSystem"),
    tenant_id: str = Query("default", alias="tenantId"),
    include_sections: list[str] | None = Query(None, alias="includeSections"),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> EffectiveIntegrationPolicyResponse:
    response = integration_service.get_effective_policy(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
        include_sections=include_sections,
    )
    return cast(EffectiveIntegrationPolicyResponse, response)
