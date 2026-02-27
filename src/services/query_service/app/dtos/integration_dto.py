from datetime import datetime

from pydantic import BaseModel, Field


class PolicyProvenanceMetadata(BaseModel):
    policy_version: str = Field(..., alias="policyVersion")
    policy_source: str = Field(..., alias="policySource")
    matched_rule_id: str = Field(..., alias="matchedRuleId")
    strict_mode: bool = Field(..., alias="strictMode")

    model_config = {"populate_by_name": True}


class EffectiveIntegrationPolicyResponse(BaseModel):
    contract_version: str = Field("v1", alias="contractVersion")
    source_service: str = Field("lotus-core", alias="sourceService")
    consumer_system: str = Field(..., alias="consumerSystem")
    tenant_id: str = Field(..., alias="tenantId")
    generated_at: datetime = Field(..., alias="generatedAt")
    policy_provenance: PolicyProvenanceMetadata = Field(..., alias="policyProvenance")
    allowed_sections: list[str] = Field(default_factory=list, alias="allowedSections")
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
