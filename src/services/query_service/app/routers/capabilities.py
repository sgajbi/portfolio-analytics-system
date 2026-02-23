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
    summary="Get PAS Integration Capabilities",
    description=(
        "Returns backend-governed PAS capability and workflow flags for a consumer system "
        "and tenant context. Intended for BFF/UI feature control and PA/DPM integration negotiation."
    ),
)
async def get_integration_capabilities(
    consumer_system: ConsumerSystem = Query(
        "BFF",
        alias="consumerSystem",
        description="Consumer requesting capability metadata (BFF, PA, DPM, UI, UNKNOWN).",
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
