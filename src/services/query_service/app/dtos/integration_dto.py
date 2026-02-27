from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyProvenanceMetadata(BaseModel):
    policy_version: str = Field(...)
    policy_source: str = Field(...)
    matched_rule_id: str = Field(...)
    strict_mode: bool = Field(...)

    model_config = ConfigDict()


class EffectiveIntegrationPolicyResponse(BaseModel):
    contract_version: str = Field("v1")
    source_service: str = Field("lotus-core")
    consumer_system: str = Field(...)
    tenant_id: str = Field(...)
    generated_at: datetime = Field(...)
    policy_provenance: PolicyProvenanceMetadata = Field(...)
    allowed_sections: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict()


class InstrumentEnrichmentBulkRequest(BaseModel):
    security_ids: list[str] = Field(
        ...,
        description="Canonical Lotus security identifiers to enrich.",
        examples=[["SEC_AAPL_US", "SEC_MSFT_US"]],
        min_length=1,
    )

    model_config = ConfigDict()


class InstrumentEnrichmentRecord(BaseModel):
    security_id: str = Field(
        ...,
        description="Canonical Lotus security identifier.",
        examples=["SEC_AAPL_US"],
    )
    issuer_id: str | None = Field(
        None,
        description="Canonical direct issuer identifier, when available.",
        examples=["ISSUER_APPLE_INC"],
    )
    issuer_name: str | None = Field(
        None,
        description="Display name for direct issuer, when available.",
        examples=["Apple Inc."],
    )
    ultimate_parent_issuer_id: str | None = Field(
        None,
        description="Canonical ultimate parent issuer identifier, when available.",
        examples=["ISSUER_APPLE_HOLDING"],
    )
    ultimate_parent_issuer_name: str | None = Field(
        None,
        description="Display name for ultimate parent issuer, when available.",
        examples=["Apple Holdings PLC"],
    )

    model_config = ConfigDict()


class InstrumentEnrichmentBulkResponse(BaseModel):
    records: list[InstrumentEnrichmentRecord] = Field(
        ...,
        description="Deterministic enrichment records in the same order as request security_ids.",
        examples=[
            [
                {
                    "security_id": "SEC_AAPL_US",
                    "issuer_id": "ISSUER_APPLE_INC",
                    "issuer_name": "Apple Inc.",
                    "ultimate_parent_issuer_id": "ISSUER_APPLE_HOLDING",
                    "ultimate_parent_issuer_name": "Apple Holdings PLC",
                }
            ]
        ],
    )

    model_config = ConfigDict()
