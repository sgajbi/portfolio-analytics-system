import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.logging_utils import correlation_id_var

from ..dtos.integration_dto import (
    CoreSnapshotLineageRefs,
    EffectiveIntegrationPolicyResponse,
    PolicyProvenanceMetadata,
    PortfolioCoreSnapshotMetadata,
    PortfolioCoreSnapshotRequest,
    PortfolioCoreSnapshotResponse,
    SectionGovernanceMetadata,
)
from ..dtos.review_dto import PortfolioReviewRequest
from .portfolio_service import PortfolioService
from .review_service import ReviewService

logger = logging.getLogger(__name__)


@dataclass
class PolicyContext:
    policy_version: str
    policy_source: str
    matched_rule_id: str
    strict_mode: bool
    allowed_sections: list[str] | None
    warnings: list[str]


class IntegrationService:
    """
    Provides PAS integration contracts for downstream services (e.g., PA, DPM).
    """

    def __init__(self, db: AsyncSession):
        self.portfolio_service = PortfolioService(db)
        self.review_service = ReviewService(db)

    @staticmethod
    def _load_policy() -> dict[str, Any]:
        raw = os.getenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON")
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid PAS_INTEGRATION_SNAPSHOT_POLICY_JSON; default policy will be used."
            )
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

    def _resolve_policy_context(
        self,
        tenant_id: str,
        consumer_system: str,
    ) -> PolicyContext:
        policy = self._load_policy()

        strict_mode = self._coerce_bool(policy.get("strictMode"), default=False)
        policy_source = "default"
        matched_rule_id = "default"
        warnings: list[str] = []

        allowed_sections = self._normalize_sections(
            policy.get("consumers", {}).get(consumer_system)
            if isinstance(policy.get("consumers"), dict)
            else None
        )
        if isinstance(policy.get("consumers"), dict) and allowed_sections is not None:
            policy_source = "global"
            matched_rule_id = f"global.consumers.{consumer_system}"

        tenants = policy.get("tenants")
        tenant_policy_raw = tenants.get(tenant_id) if isinstance(tenants, dict) else None
        if isinstance(tenant_policy_raw, dict):
            strict_mode = self._coerce_bool(
                tenant_policy_raw.get("strictMode"), default=strict_mode
            )
            tenant_consumers = tenant_policy_raw.get("consumers")
            tenant_allowed = self._normalize_sections(
                tenant_consumers.get(consumer_system)
                if isinstance(tenant_consumers, dict)
                else tenant_policy_raw.get("defaultSections")
            )
            if tenant_allowed is not None:
                allowed_sections = tenant_allowed
                policy_source = "tenant"
                matched_rule_id = f"tenant.{tenant_id}.consumers.{consumer_system}"
            elif isinstance(tenant_policy_raw.get("defaultSections"), list):
                policy_source = "tenant"
                matched_rule_id = f"tenant.{tenant_id}.defaultSections"
            if "strictMode" in tenant_policy_raw:
                policy_source = "tenant"
                if matched_rule_id == "default":
                    matched_rule_id = f"tenant.{tenant_id}.strictMode"

        if allowed_sections is None:
            warnings.append("NO_ALLOWED_SECTION_OVERRIDE")

        return PolicyContext(
            policy_version=os.getenv("PAS_POLICY_VERSION", "tenant-default-v1"),
            policy_source=policy_source,
            matched_rule_id=matched_rule_id,
            strict_mode=strict_mode,
            allowed_sections=allowed_sections,
            warnings=warnings,
        )

    def _resolve_governance(
        self,
        requested_sections: list[str],
        context: PolicyContext,
    ) -> SectionGovernanceMetadata:
        if context.allowed_sections is None:
            effective_sections = list(requested_sections)
        else:
            allowed_set = set(context.allowed_sections)
            effective_sections = [
                section for section in requested_sections if section in allowed_set
            ]
        dropped_sections = [
            section for section in requested_sections if section not in set(effective_sections)
        ]
        warnings: list[str] = list(context.warnings)
        if dropped_sections:
            if context.strict_mode:
                dropped = ", ".join(dropped_sections)
                raise PermissionError(
                    f"Requested sections are not allowed by PAS snapshot policy: {dropped}"
                )
            warnings.append("SECTIONS_FILTERED_BY_POLICY")

        return SectionGovernanceMetadata(
            requestedSections=requested_sections,
            effectiveSections=effective_sections,
            droppedSections=dropped_sections,
            warnings=warnings,
        )

    @staticmethod
    def _resolve_freshness_status(as_of_date: date) -> str:
        max_staleness_days = int(os.getenv("PAS_INTEGRATION_MAX_STALENESS_DAYS", "1"))
        today = date.today()
        if as_of_date > today:
            return "UNKNOWN"
        age_days = (today - as_of_date).days
        if age_days <= max_staleness_days:
            return "FRESH"
        return "STALE"

    async def get_portfolio_core_snapshot(
        self, portfolio_id: str, request: PortfolioCoreSnapshotRequest
    ) -> PortfolioCoreSnapshotResponse:
        consumer_system = (request.consumer_system or "UNKNOWN").upper()
        tenant_id = os.getenv("PAS_DEFAULT_TENANT_ID", "default")
        requested_sections = [section.value for section in request.include_sections]
        policy_context = self._resolve_policy_context(
            tenant_id=tenant_id,
            consumer_system=consumer_system,
        )
        governance = self._resolve_governance(
            requested_sections=requested_sections,
            context=policy_context,
        )
        effective_sections = governance.effective_sections

        if not effective_sections:
            raise PermissionError(
                "No includeSections are allowed by PAS snapshot policy for the current context."
            )

        portfolio = await self.portfolio_service.get_portfolio_by_id(portfolio_id)

        review_request = PortfolioReviewRequest(
            as_of_date=request.as_of_date,
            sections=effective_sections,
        )
        snapshot = await self.review_service.get_portfolio_review(portfolio_id, review_request)

        metadata = PortfolioCoreSnapshotMetadata(
            generatedAt=datetime.now(UTC),
            sourceAsOfDate=request.as_of_date,
            freshnessStatus=self._resolve_freshness_status(request.as_of_date),
            lineageRefs=CoreSnapshotLineageRefs(
                portfolioId=portfolio_id,
                asOfDate=request.as_of_date,
                correlationId=correlation_id_var.get(),
            ),
            sectionGovernance=governance,
            policyProvenance=PolicyProvenanceMetadata(
                policyVersion=policy_context.policy_version,
                policySource=policy_context.policy_source,
                matchedRuleId=policy_context.matched_rule_id,
                strictMode=policy_context.strict_mode,
            ),
        )

        return PortfolioCoreSnapshotResponse(
            consumerSystem=consumer_system,
            portfolio=portfolio,
            snapshot=snapshot,
            metadata=metadata,
        )

    def get_effective_policy(
        self,
        consumer_system: str,
        tenant_id: str,
        include_sections: list[str] | None,
    ) -> EffectiveIntegrationPolicyResponse:
        normalized_consumer = consumer_system.upper()
        policy_context = self._resolve_policy_context(
            tenant_id=tenant_id,
            consumer_system=normalized_consumer,
        )

        if include_sections:
            requested_sections = [section.upper() for section in include_sections]
            governance = self._resolve_governance(
                requested_sections=requested_sections,
                context=policy_context,
            )
            allowed_sections = governance.effective_sections
            warnings = governance.warnings
        elif policy_context.allowed_sections is not None:
            allowed_sections = policy_context.allowed_sections
            warnings = list(policy_context.warnings)
        else:
            allowed_sections = []
            warnings = list(policy_context.warnings)
            warnings.append("NO_ALLOWED_SECTION_RESTRICTION")

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
            warnings=warnings,
        )
