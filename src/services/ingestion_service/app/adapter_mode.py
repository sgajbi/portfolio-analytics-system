import os

from fastapi import HTTPException, status


def _env_enabled(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def portfolio_bundle_adapter_enabled() -> bool:
    return _env_enabled("LOTUS_CORE_INGEST_PORTFOLIO_BUNDLE_ENABLED", "true")


def upload_adapter_enabled() -> bool:
    return _env_enabled("LOTUS_CORE_INGEST_UPLOAD_APIS_ENABLED", "true")


def require_portfolio_bundle_adapter_enabled() -> None:
    if portfolio_bundle_adapter_enabled():
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "LOTUS_CORE_ADAPTER_MODE_DISABLED",
            "capability": "lotus_core.ingestion.portfolio_bundle_adapter",
            "message": (
                "Portfolio bundle adapter mode is disabled. "
                "Use canonical ingestion endpoints (/ingest/portfolios, /ingest/transactions, "
                "/ingest/instruments, /ingest/market-prices, /ingest/fx-rates, /ingest/business-dates)."
            ),
        },
    )


def require_upload_adapter_enabled() -> None:
    if upload_adapter_enabled():
        return
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "LOTUS_CORE_ADAPTER_MODE_DISABLED",
            "capability": "lotus_core.ingestion.bulk_upload_adapter",
            "message": (
                "Bulk upload adapter mode is disabled. "
                "Use canonical ingestion endpoints for production upstream integration."
            ),
        },
    )
