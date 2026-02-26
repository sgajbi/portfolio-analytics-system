import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from portfolio_common.logging_utils import correlation_id_var
from sqlalchemy.ext.asyncio import AsyncSession

from ..dtos.integration_dto import (
    CoreSnapshotLineageRefs,
    EffectiveIntegrationPolicyResponse,
    PolicyProvenanceMetadata,
    PortfolioCoreSnapshotMetadata,
    PortfolioCoreSnapshotRequest,
    PortfolioCoreSnapshotResponse,
    PortfolioPerformanceInputPoint,
    PortfolioPerformanceInputRequest,
    PortfolioPerformanceInputResponse,
    SectionGovernanceMetadata,
)
from ..dtos.review_dto import PortfolioReviewRequest
from ..repositories.performance_repository import PerformanceRepository
from .portfolio_service import PortfolioService
from .review_service import ReviewService

logger = logging.getLogger(__name__)

_PAS_CORE_SNAPSHOT_ANALYTICS_OWNERSHIP_RESTRICTED: set[str] = {
    "PERFORMANCE",
    "RISK_ANALYTICS",
}

_CONSUMER_CANONICAL_MAP: dict[str, str] = {
    "PA": "lotus-performance",
    "LOTUS-PERFORMANCE": "lotus-performance",
    "PAS": "lotus-core",
    "LOTUS-CORE": "lotus-core",
    "DPM": "lotus-manage",
    "LOTUS-MANAGE": "lotus-manage",
    "LOTUS-ADVISE": "lotus-advise",
    "RAS": "lotus-report",
    "LOTUS-REPORT": "lotus-report",
    "BFF": "lotus-gateway",
    "AEA": "lotus-gateway",
    "LOTUS-GATEWAY": "lotus-gateway",
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
    """
    Provides lotus-core integration contracts for downstream services (e.g., lotus-performance, lotus-manage).
    """

    def __init__(self, db: AsyncSession):
        self.portfolio_service = PortfolioService(db)
        self.review_service = ReviewService(db)
        self.performance_repository = PerformanceRepository(db)

    @staticmethod
    def _read_attr_or_key(target: Any, key: str, default: Any = None) -> Any:
        if hasattr(target, key):
            return getattr(target, key)
        if isinstance(target, dict):
            return target.get(key, default)
        return default
    @staticmethod
    def _canonical_consumer_system(value: str | None) -> str:
        raw = (value or "UNKNOWN").strip()
        if not raw:
            return "unknown"
        key = raw.upper()
        return _CONSUMER_CANONICAL_MAP.get(key, raw.lower())

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
                tenant_allowed = self._normalize_sections(
                    tenant_policy_raw.get("defaultSections")
                )
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
                    f"Requested sections are not allowed by lotus-core snapshot policy: {dropped}"
                )
            warnings.append("SECTIONS_FILTERED_BY_POLICY")

        ownership_restricted = [
            section
            for section in effective_sections
            if section in _PAS_CORE_SNAPSHOT_ANALYTICS_OWNERSHIP_RESTRICTED
        ]
        if ownership_restricted:
            if context.strict_mode:
                blocked = ", ".join(ownership_restricted)
                raise PermissionError(
                    "Requested analytics sections are not owned by lotus-core core snapshot contract: "
                    f"{blocked}"
                )
            effective_sections = [
                section for section in effective_sections if section not in ownership_restricted
            ]
            dropped_sections.extend(ownership_restricted)
            warnings.append("ANALYTICS_SECTIONS_DELEGATED_TO_PA")

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
        consumer_system = self._canonical_consumer_system(request.consumer_system)
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
                "No includeSections are allowed by lotus-core snapshot policy for the current context."
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

    async def get_portfolio_performance_input(
        self,
        portfolio_id: str,
        request: PortfolioPerformanceInputRequest,
    ) -> PortfolioPerformanceInputResponse:
        consumer_system = self._canonical_consumer_system(request.consumer_system)
        portfolio = await self.portfolio_service.get_portfolio_by_id(portfolio_id)

        start_date = max(
            self._read_attr_or_key(portfolio, "open_date"),
            request.as_of_date - timedelta(days=request.lookback_days),
        )
        rows = await self.performance_repository.get_portfolio_timeseries_for_range(
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=request.as_of_date,
        )
        if not rows:
            raise ValueError(
                f"No portfolio_timeseries rows found for {portfolio_id} up to {request.as_of_date}."
            )

        points: list[PortfolioPerformanceInputPoint] = []
        for index, row in enumerate(rows, start=1):
            points.append(
                PortfolioPerformanceInputPoint(
                    day=index,
                    perfDate=row.date,
                    beginMv=float(row.bod_market_value),
                    bodCf=float(row.bod_cashflow),
                    eodCf=float(row.eod_cashflow),
                    mgmtFees=float(row.fees),
                    endMv=float(row.eod_market_value),
                )
            )

        performance_start_date = points[0].perf_date
        return PortfolioPerformanceInputResponse(
            consumerSystem=consumer_system,
            portfolioId=self._read_attr_or_key(portfolio, "portfolio_id"),
            baseCurrency=self._read_attr_or_key(portfolio, "base_currency"),
            performanceStartDate=performance_start_date,
            asOfDate=request.as_of_date,
            valuationPoints=points,
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
            requested_sections = [section.upper() for section in include_sections]
            if (
                policy_context.policy_source == "tenant"
                and policy_context.matched_rule_id.endswith(".defaultSections")
            ):
                # Tenant defaults are advisory for policy visibility, not hard filters
                # when the caller explicitly requests include sections.
                allowed_sections = requested_sections
                warnings = list(policy_context.warnings)
            else:
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
