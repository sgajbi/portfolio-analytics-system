from fastapi import APIRouter, Depends, Query
from typing import cast

from ..dtos.capabilities_dto import ConsumerSystem, IntegrationCapabilitiesResponse
from ..services.capabilities_service import CapabilitiesService

router = APIRouter(prefix="/integration", tags=["Integration"])


def get_capabilities_service() -> CapabilitiesService:
    return CapabilitiesService()


@router.get(
    "/capabilities",
    response_model=IntegrationCapabilitiesResponse,
    summary="Get lotus-core Integration Capabilities",
    description=(
        "Returns backend-governed lotus-core capability and workflow flags for a consumer system "
        "and tenant context. Intended for lotus-gateway/UI and lotus-manage feature control."
    ),
)
async def get_integration_capabilities(
    consumer_system: ConsumerSystem = Query(
        "lotus-gateway",
        alias="consumerSystem",
        description="Consumer requesting capability metadata (lotus-gateway, lotus-manage, UI, UNKNOWN).",
    ),
    tenant_id: str = Query(
        "default",
        alias="tenantId",
        description="Tenant or client identifier for policy resolution.",
    ),
    service: CapabilitiesService = Depends(get_capabilities_service),
) -> IntegrationCapabilitiesResponse:
    capabilities_service: CapabilitiesService = service
    response = capabilities_service.get_integration_capabilities(
        consumer_system=consumer_system,
        tenant_id=tenant_id,
    )
    return cast(IntegrationCapabilitiesResponse, response)
