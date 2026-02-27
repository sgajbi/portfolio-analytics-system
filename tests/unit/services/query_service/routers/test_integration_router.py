import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)
from src.services.query_service.app.routers.integration import (
    create_core_snapshot,
    get_core_snapshot_service,
    get_effective_integration_policy,
    get_integration_service,
)
from src.services.query_service.app.services.core_snapshot_service import CoreSnapshotService
from src.services.query_service.app.services.core_snapshot_service import CoreSnapshotNotFoundError
from src.services.query_service.app.services.integration_service import IntegrationService


@pytest.mark.asyncio
async def test_get_effective_integration_policy_router_function() -> None:
    mock_service = MagicMock(spec=IntegrationService)
    mock_service.get_effective_policy.return_value = {
        "contract_version": "v1",
        "source_service": "lotus-core",
        "consumer_system": "lotus-manage",
        "tenant_id": "tenant-a",
        "generated_at": "2026-02-27T00:00:00Z",
        "policy_provenance": {
            "policy_version": "tenant-default-v1",
            "policy_source": "default",
            "matched_rule_id": "default",
            "strict_mode": False,
        },
        "allowed_sections": ["OVERVIEW"],
        "warnings": [],
    }

    response = await get_effective_integration_policy(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
        integration_service=mock_service,
    )

    mock_service.get_effective_policy.assert_called_once_with(
        consumer_system="lotus-manage",
        tenant_id="tenant-a",
        include_sections=["OVERVIEW"],
    )
    assert response["consumer_system"] == "lotus-manage"


def test_get_integration_service_factory_returns_service() -> None:
    service = get_integration_service(db=MagicMock())
    assert isinstance(service, IntegrationService)


def test_get_core_snapshot_service_factory_returns_service() -> None:
    service = get_core_snapshot_service(db=MagicMock())
    assert isinstance(service, CoreSnapshotService)


@pytest.mark.asyncio
async def test_create_core_snapshot_router_function() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )
    mock_service.get_core_snapshot.return_value = {
        "portfolio_id": "PORT_001",
        "as_of_date": "2026-02-27",
        "snapshot_mode": "BASELINE",
        "generated_at": "2026-02-27T00:00:00Z",
        "valuation_context": {
            "portfolio_currency": "USD",
            "reporting_currency": "USD",
            "position_basis": "market_value_base",
            "weight_basis": "total_market_value_base",
        },
        "sections": {"positions_baseline": []},
    }

    response = await create_core_snapshot(
        portfolio_id="PORT_001",
        request=request,
        service=mock_service,
    )

    mock_service.get_core_snapshot.assert_called_once()
    assert response["portfolio_id"] == "PORT_001"


@pytest.mark.asyncio
async def test_create_core_snapshot_maps_not_found_to_404() -> None:
    mock_service = MagicMock(spec=CoreSnapshotService)
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )
    mock_service.get_core_snapshot.side_effect = CoreSnapshotNotFoundError("not found")

    with pytest.raises(HTTPException) as exc_info:
        await create_core_snapshot(
            portfolio_id="PORT_404",
            request=request,
            service=mock_service,
        )

    assert exc_info.value.status_code == 404

