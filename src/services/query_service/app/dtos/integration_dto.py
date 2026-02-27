from datetime import datetime

from pydantic import BaseModel, Field


class PolicyProvenanceMetadata(BaseModel):
    policy_version: str = Field(...)
    policy_source: str = Field(...)
    matched_rule_id: str = Field(...)
    strict_mode: bool = Field(...)

    model_config = {}


class EffectiveIntegrationPolicyResponse(BaseModel):
    contract_version: str = Field("v1")
    source_service: str = Field("lotus-core")
    consumer_system: str = Field(...)
    tenant_id: str = Field(...)
    generated_at: datetime = Field(...)
    policy_provenance: PolicyProvenanceMetadata = Field(...)
    allowed_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {}

