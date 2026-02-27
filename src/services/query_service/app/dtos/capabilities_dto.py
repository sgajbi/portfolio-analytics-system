from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


ConsumerSystem = Literal["lotus-gateway", "lotus-performance", "lotus-manage", "UI", "UNKNOWN"]


class FeatureCapability(BaseModel):
    key: str = Field(..., description="Canonical feature key.")
    enabled: bool = Field(..., description="Whether this feature is enabled.")
    owner_service: str = Field(..., description="Owning service for the feature capability.")
    description: str = Field(..., description="Human-readable capability summary.")


class WorkflowCapability(BaseModel):
    workflow_key: str = Field(..., description="Workflow identifier.")
    enabled: bool = Field(..., description="Whether workflow is enabled for current context.")
    required_features: list[str] = Field(
        default_factory=list, description="Feature keys required for workflow execution."
    )


class IntegrationCapabilitiesResponse(BaseModel):
    contract_version: str = Field(...)
    source_service: str = Field(...)
    consumer_system: ConsumerSystem = Field(...)
    tenant_id: str = Field(...)
    generated_at: datetime = Field(...)
    as_of_date: date = Field(...)
    policy_version: str = Field(...)
    supported_input_modes: list[str] = Field(...)
    features: list[FeatureCapability]
    workflows: list[WorkflowCapability]

    model_config = {
        "json_schema_extra": {
            "example": {
                "contract_version": "v1",
                "source_service": "lotus-core",
                "consumer_system": "lotus-gateway",
                "tenant_id": "default",
                "generated_at": "2026-02-23T21:00:00Z",
                "as_of_date": "2026-02-23",
                "policy_version": "tenant-default-v1",
                "supported_input_modes": ["lotus_core_ref", "inline_bundle"],
                "features": [
                    {
                        "key": "lotus_core.support.overview_api",
                        "enabled": True,
                        "owner_service": "lotus-core",
                        "description": "Support diagnostics and operational support APIs.",
                    }
                ],
                "workflows": [
                    {
                        "workflow_key": "advisor_workbench_overview",
                        "enabled": True,
                        "required_features": [
                            "lotus_core.integration.core_snapshot",
                            "lotus_core.support.overview_api",
                        ],
                    }
                ],
            }
        },
    }

