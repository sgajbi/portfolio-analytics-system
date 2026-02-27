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
                "contractVersion": "v1",
                "sourceService": "lotus-core",
                "consumerSystem": "lotus-gateway",
                "tenantId": "default",
                "generatedAt": "2026-02-23T21:00:00Z",
                "asOfDate": "2026-02-23",
                "policyVersion": "tenant-default-v1",
                "supportedInputModes": ["pas_ref", "inline_bundle"],
                "features": [
                    {
                        "key": "pas.support.overview_api",
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
                            "pas.integration.core_snapshot",
                            "pas.support.overview_api",
                        ],
                    }
                ],
            }
        },
    }

