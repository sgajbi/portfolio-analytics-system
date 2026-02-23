from __future__ import annotations

import os
from datetime import UTC, date, datetime

from ..dtos.capabilities_dto import (
    ConsumerSystem,
    FeatureCapability,
    IntegrationCapabilitiesResponse,
    WorkflowCapability,
)


class CapabilitiesService:
    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def get_integration_capabilities(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> IntegrationCapabilitiesResponse:
        core_snapshot_enabled = self._env_bool("PAS_CAP_CORE_SNAPSHOT_ENABLED", True)
        support_apis_enabled = self._env_bool("PAS_CAP_SUPPORT_APIS_ENABLED", True)
        lineage_apis_enabled = self._env_bool("PAS_CAP_LINEAGE_APIS_ENABLED", True)
        upload_preview_commit_enabled = self._env_bool("PAS_CAP_UPLOAD_APIS_ENABLED", True)
        baseline_performance_enabled = self._env_bool("PAS_CAP_BASELINE_PERFORMANCE_ENABLED", True)
        baseline_risk_enabled = self._env_bool("PAS_CAP_BASELINE_RISK_ENABLED", True)

        features = [
            FeatureCapability(
                key="pas.integration.core_snapshot",
                enabled=core_snapshot_enabled,
                owner_service="PAS",
                description="Core portfolio snapshot API for PA, DPM, and BFF.",
            ),
            FeatureCapability(
                key="pas.support.overview_api",
                enabled=support_apis_enabled,
                owner_service="PAS",
                description="Support diagnostics and operational support APIs.",
            ),
            FeatureCapability(
                key="pas.support.lineage_api",
                enabled=lineage_apis_enabled,
                owner_service="PAS",
                description="Lineage and epoch/watermark traceability APIs.",
            ),
            FeatureCapability(
                key="pas.ingestion.bulk_upload",
                enabled=upload_preview_commit_enabled,
                owner_service="PAS",
                description="CSV/XLSX preview+commit onboarding APIs.",
            ),
            FeatureCapability(
                key="pas.analytics.baseline_performance",
                enabled=baseline_performance_enabled,
                owner_service="PAS",
                description="Baseline performance metrics owned by PAS.",
            ),
            FeatureCapability(
                key="pas.analytics.baseline_risk",
                enabled=baseline_risk_enabled,
                owner_service="PAS",
                description="Baseline risk metrics owned by PAS.",
            ),
        ]

        workflows = [
            WorkflowCapability(
                workflow_key="advisor_workbench_overview",
                enabled=core_snapshot_enabled and support_apis_enabled,
                required_features=[
                    "pas.integration.core_snapshot",
                    "pas.support.overview_api",
                ],
            ),
            WorkflowCapability(
                workflow_key="analytics_baseline_snapshot",
                enabled=baseline_performance_enabled and baseline_risk_enabled,
                required_features=[
                    "pas.analytics.baseline_performance",
                    "pas.analytics.baseline_risk",
                ],
            ),
            WorkflowCapability(
                workflow_key="portfolio_bulk_onboarding",
                enabled=upload_preview_commit_enabled,
                required_features=["pas.ingestion.bulk_upload"],
            ),
        ]

        if consumer_system in {"PA", "DPM"}:
            supported_input_modes = ["pas_ref", "inline_bundle"]
        else:
            supported_input_modes = ["pas_ref"]

        return IntegrationCapabilitiesResponse(
            contractVersion="v1",
            sourceService="portfolio-analytics-system",
            consumerSystem=consumer_system,
            tenantId=tenant_id,
            generatedAt=datetime.now(UTC),
            asOfDate=date.today(),
            policyVersion=os.getenv("PAS_POLICY_VERSION", "tenant-default-v1"),
            supportedInputModes=supported_input_modes,
            features=features,
            workflows=workflows,
        )
