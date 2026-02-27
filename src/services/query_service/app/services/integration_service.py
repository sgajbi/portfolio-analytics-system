import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.integration_dto import EffectiveIntegrationPolicyResponse, PolicyProvenanceMetadata

logger = logging.getLogger(__name__)

_CONSUMER_CANONICAL_MAP: dict[str, str] = {
    "LOTUS-MANAGE": "lotus-manage",
    "DPM": "lotus-manage",
    "LOTUS-GATEWAY": "lotus-gateway",
    "AEA": "lotus-gateway",
    "BFF": "lotus-gateway",
    "UI": "UI",
}


@dataclass
class PolicyContext:
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    allowed_sections: list[str] | None
    warnings: list[str]


class IntegrationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _canonical_consumer_system(value: str | None) -> str:
        raw = (value or "UNKNOWN").strip()
        if not raw:
            return "unknown"
        key = raw.upper()
        return _CONSUMER_CANONICAL_MAP.get(key, raw.lower())

    @staticmethod
    def _load_policy() -> dict[str, Any]:
        raw = os.getenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON")
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid PAS_INTEGRATION_SNAPSHOT_POLICY_JSON; using defaults.")
            return {}
        if not isinstance(decoded, dict):
            return {}
        return decoded

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def _normalize_sections(raw: Any) -> list[str] | None:
        if not isinstance(raw, list):
            return None
        normalized: list[str] = []
        for item in raw:
            if isinstance(item, str):
                value = item.strip().upper()
                if value:
                    normalized.append(value)
        return normalized

    @staticmethod
    def _resolve_consumer_sections(
        consumers: dict[str, Any] | None,
        consumer_system: str,
    ) -> tuple[list[str] | None, str | None]:
        if not isinstance(consumers, dict):
            return None, None
        canonical = IntegrationService._canonical_consumer_system(consumer_system)
        for key, value in consumers.items():
            if IntegrationService._canonical_consumer_system(str(key)) == canonical:
                return IntegrationService._normalize_sections(value), str(key)
        return None, None

    def _resolve_policy_context(self, tenant_id: str, consumer_system: str) -> PolicyContext:
        policy = self._load_policy()

        strict_mode = self._coerce_bool(policy.get("strictMode"), default=False)
        policy_source = "default"
        matched_rule_id = "default"
        warnings: list[str] = []

        allowed_sections, matched_consumer_key = self._resolve_consumer_sections(
            policy.get("consumers"),
            consumer_system,
        )
        if allowed_sections is not None:
            policy_source = "global"
            matched_rule_id = f"global.consumers.{matched_consumer_key}"

        tenants = policy.get("tenants")
        tenant_policy_raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
        if isinstance(tenant_policy_raw, dict):
            strict_mode = self._coerce_bool(
                tenant_policy_raw.get("strictMode"), default=strict_mode
            )
            tenant_consumers = tenant_policy_raw.get("consumers")
            tenant_allowed, tenant_match_key = self._resolve_consumer_sections(
                tenant_consumers if isinstance(tenant_consumers, dict) else None,
                consumer_system,
            )
            if tenant_allowed is None:
                tenant_allowed = self._normalize_sections(tenant_policy_raw.get("defaultSections"))
            if tenant_allowed is not None:
                allowed_sections = tenant_allowed
                policy_source = "tenant"
                if tenant_match_key is not None:
                    matched_rule_id = f"tenant.{tenant_id}.consumers.{tenant_match_key}"
                else:
                    matched_rule_id = f"tenant.{tenant_id}.defaultSections"
            elif isinstance(tenant_policy_raw.get("defaultSections"), list):
                policy_source = "tenant"
                matched_rule_id = f"tenant.{tenant_id}.defaultSections"
            if "strictMode" in tenant_policy_raw and matched_rule_id == "default":
                policy_source = "tenant"
                matched_rule_id = f"tenant.{tenant_id}.strictMode"

        if allowed_sections is None:
            warnings.append("NO_ALLOWED_SECTION_RESTRICTION")

        return PolicyContext(
            policy_version=os.getenv("PAS_POLICY_VERSION", "tenant-default-v1"),
            policy_source=policy_source,
            matched_rule_id=matched_rule_id,
            strict_mode=strict_mode,
            allowed_sections=allowed_sections,
            warnings=warnings,
        )

    def get_effective_policy(
        self,
        consumer_system: str,
        tenant_id: str,
        include_sections: list[str] | None,
    ) -> EffectiveIntegrationPolicyResponse:
        normalized_consumer = self._canonical_consumer_system(consumer_system)
        policy_context = self._resolve_policy_context(
            tenant_id=tenant_id,
            consumer_system=normalized_consumer,
        )

        if include_sections:
            requested = [section.upper() for section in include_sections]
            if policy_context.allowed_sections is None:
                allowed_sections = requested
            else:
                allowed_set = set(policy_context.allowed_sections)
                allowed_sections = [section for section in requested if section in allowed_set]
        elif policy_context.allowed_sections is not None:
            allowed_sections = policy_context.allowed_sections
        else:
            allowed_sections = []

        return EffectiveIntegrationPolicyResponse(
            consumerSystem=normalized_consumer,
            tenantId=tenant_id,
            generatedAt=datetime.now(UTC),
            policyProvenance=PolicyProvenanceMetadata(
                policyVersion=policy_context.policy_version,
                policySource=policy_context.policy_source,
                matchedRuleId=policy_context.matched_rule_id,
                strictMode=policy_context.strict_mode,
            ),
            allowedSections=allowed_sections,
            warnings=policy_context.warnings,
        )
