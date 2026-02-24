from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime
from typing import Any

from ..dtos.capabilities_dto import (
    ConsumerSystem,
    FeatureCapability,
    IntegrationCapabilitiesResponse,
    WorkflowCapability,
)


logger = logging.getLogger(__name__)


_FEATURE_ENV_DEFAULTS: dict[str, tuple[str, bool]] = {
    "pas.integration.core_snapshot": ("PAS_CAP_CORE_SNAPSHOT_ENABLED", True),
    "pas.support.overview_api": ("PAS_CAP_SUPPORT_APIS_ENABLED", True),
    "pas.support.lineage_api": ("PAS_CAP_LINEAGE_APIS_ENABLED", True),
    "pas.ingestion.bulk_upload": ("PAS_CAP_UPLOAD_APIS_ENABLED", True),
    "pas.analytics.baseline_performance": ("PAS_CAP_BASELINE_PERFORMANCE_ENABLED", True),
    "pas.analytics.baseline_risk": ("PAS_CAP_BASELINE_RISK_ENABLED", True),
}

_WORKFLOW_DEPENDENCIES: dict[str, list[str]] = {
    "advisor_workbench_overview": [
        "pas.integration.core_snapshot",
        "pas.support.overview_api",
    ],
    "analytics_baseline_snapshot": [
        "pas.analytics.baseline_performance",
        "pas.analytics.baseline_risk",
    ],
    "portfolio_bulk_onboarding": ["pas.ingestion.bulk_upload"],
}

_DEFAULT_INPUT_MODES_BY_CONSUMER: dict[str, list[str]] = {
    "PA": ["pas_ref", "inline_bundle"],
    "DPM": ["pas_ref", "inline_bundle"],
    "BFF": ["pas_ref"],
    "UI": ["pas_ref"],
    "UNKNOWN": ["pas_ref"],
}


class CapabilitiesService:
    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _load_tenant_overrides() -> dict[str, dict[str, Any]]:
        raw = os.getenv("PAS_CAPABILITY_TENANT_OVERRIDES_JSON")
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid PAS_CAPABILITY_TENANT_OVERRIDES_JSON; ignoring tenant overrides.",
            )
            return {}

        if not isinstance(decoded, dict):
            logger.warning(
                "PAS_CAPABILITY_TENANT_OVERRIDES_JSON must be a JSON object; ignoring tenant overrides.",
            )
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for tenant_id, policy in decoded.items():
            if not isinstance(tenant_id, str) or not isinstance(policy, dict):
                continue
            normalized[tenant_id] = policy
        return normalized

    def get_integration_capabilities(
        self,
        consumer_system: ConsumerSystem,
        tenant_id: str,
    ) -> IntegrationCapabilitiesResponse:
        feature_states: dict[str, bool] = {
            key: self._env_bool(env_name, default)
            for key, (env_name, default) in _FEATURE_ENV_DEFAULTS.items()
        }
        policy_version = os.getenv("PAS_POLICY_VERSION", "tenant-default-v1")
        supported_input_modes = list(
            _DEFAULT_INPUT_MODES_BY_CONSUMER.get(consumer_system, ["pas_ref"])
        )

        tenant_policy = self._load_tenant_overrides().get(tenant_id)
        if tenant_policy:
            feature_overrides = tenant_policy.get("features", {})
            if isinstance(feature_overrides, dict):
                for key, value in feature_overrides.items():
                    if key in feature_states and isinstance(value, bool):
                        feature_states[key] = value

            workflow_overrides = tenant_policy.get("workflows", {})
            policy_workflow_overrides: dict[str, bool] = {}
            if isinstance(workflow_overrides, dict):
                for key, value in workflow_overrides.items():
                    if key in _WORKFLOW_DEPENDENCIES and isinstance(value, bool):
                        policy_workflow_overrides[key] = value
            else:
                policy_workflow_overrides = {}

            tenant_policy_version = tenant_policy.get("policyVersion")
            if isinstance(tenant_policy_version, str) and tenant_policy_version.strip():
                policy_version = tenant_policy_version.strip()

            input_modes = tenant_policy.get("supportedInputModes", {})
            if isinstance(input_modes, dict):
                consumer_modes = input_modes.get(consumer_system)
                fallback_modes = input_modes.get("default")
                mode_source = consumer_modes if isinstance(consumer_modes, list) else fallback_modes
                if isinstance(mode_source, list):
                    normalized_modes = [
                        mode for mode in mode_source if isinstance(mode, str) and mode.strip()
                    ]
                    if normalized_modes:
                        supported_input_modes = normalized_modes
        else:
            policy_workflow_overrides = {}

        features = [
            FeatureCapability(
                key="pas.integration.core_snapshot",
                enabled=feature_states["pas.integration.core_snapshot"],
                owner_service="PAS",
                description="Core portfolio snapshot API for PA, DPM, and BFF.",
            ),
            FeatureCapability(
                key="pas.support.overview_api",
                enabled=feature_states["pas.support.overview_api"],
                owner_service="PAS",
                description="Support diagnostics and operational support APIs.",
            ),
            FeatureCapability(
                key="pas.support.lineage_api",
                enabled=feature_states["pas.support.lineage_api"],
                owner_service="PAS",
                description="Lineage and epoch/watermark traceability APIs.",
            ),
            FeatureCapability(
                key="pas.ingestion.bulk_upload",
                enabled=feature_states["pas.ingestion.bulk_upload"],
                owner_service="PAS",
                description="CSV/XLSX preview+commit onboarding APIs.",
            ),
            FeatureCapability(
                key="pas.analytics.baseline_performance",
                enabled=feature_states["pas.analytics.baseline_performance"],
                owner_service="PAS",
                description="Baseline performance metrics owned by PAS.",
            ),
            FeatureCapability(
                key="pas.analytics.baseline_risk",
                enabled=feature_states["pas.analytics.baseline_risk"],
                owner_service="PAS",
                description="Baseline risk metrics owned by PAS.",
            ),
        ]

        workflows = [
            WorkflowCapability(
                workflow_key="advisor_workbench_overview",
                enabled=policy_workflow_overrides.get(
                    "advisor_workbench_overview",
                    all(feature_states[key] for key in _WORKFLOW_DEPENDENCIES["advisor_workbench_overview"]),
                ),
                required_features=[
                    "pas.integration.core_snapshot",
                    "pas.support.overview_api",
                ],
            ),
            WorkflowCapability(
                workflow_key="analytics_baseline_snapshot",
                enabled=policy_workflow_overrides.get(
                    "analytics_baseline_snapshot",
                    all(feature_states[key] for key in _WORKFLOW_DEPENDENCIES["analytics_baseline_snapshot"]),
                ),
                required_features=[
                    "pas.analytics.baseline_performance",
                    "pas.analytics.baseline_risk",
                ],
            ),
            WorkflowCapability(
                workflow_key="portfolio_bulk_onboarding",
                enabled=policy_workflow_overrides.get(
                    "portfolio_bulk_onboarding",
                    all(feature_states[key] for key in _WORKFLOW_DEPENDENCIES["portfolio_bulk_onboarding"]),
                ),
                required_features=["pas.ingestion.bulk_upload"],
            ),
        ]

        return IntegrationCapabilitiesResponse(
            contractVersion="v1",
            sourceService="portfolio-analytics-system",
            consumerSystem=consumer_system,
            tenantId=tenant_id,
            generatedAt=datetime.now(UTC),
            asOfDate=date.today(),
            policyVersion=policy_version,
            supportedInputModes=supported_input_modes,
            features=features,
            workflows=workflows,
        )
