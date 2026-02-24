import json
import logging
import os
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_common.logging_utils import correlation_id_var

from ..dtos.integration_dto import (
    CoreSnapshotLineageRefs,
    PortfolioCoreSnapshotMetadata,
    PortfolioCoreSnapshotRequest,
    PortfolioCoreSnapshotResponse,
    SectionGovernanceMetadata,
)
from ..dtos.review_dto import PortfolioReviewRequest
from .portfolio_service import PortfolioService
from .review_service import ReviewService

logger = logging.getLogger(__name__)


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

    def _resolve_governance(
        self,
        tenant_id: str,
        consumer_system: str,
        requested_sections: list[str],
    ) -> SectionGovernanceMetadata:
        policy = self._load_policy()

        strict_mode = self._coerce_bool(policy.get("strictMode"), default=False)
        allowed_sections = self._normalize_sections(
            policy.get("consumers", {}).get(consumer_system)
            if isinstance(policy.get("consumers"), dict)
            else None
        )

        tenant_policy_raw = policy.get("tenants", {}).get(tenant_id)
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

        if allowed_sections is None:
            effective_sections = list(requested_sections)
        else:
            allowed_set = set(allowed_sections)
            effective_sections = [
                section for section in requested_sections if section in allowed_set
            ]

        dropped_sections = [
            section for section in requested_sections if section not in set(effective_sections)
        ]
        warnings: list[str] = []
        if dropped_sections:
            if strict_mode:
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
        governance = self._resolve_governance(
            tenant_id=tenant_id,
            consumer_system=consumer_system,
            requested_sections=requested_sections,
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
        )

        return PortfolioCoreSnapshotResponse(
            consumerSystem=consumer_system,
            portfolio=portfolio,
            snapshot=snapshot,
            metadata=metadata,
        )
