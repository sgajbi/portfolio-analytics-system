from fastapi import HTTPException, status


def raise_legacy_endpoint_gone(
    *,
    capability: str,
    target_service: str,
    target_endpoint: str,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "PAS_LEGACY_ENDPOINT_REMOVED",
            "capability": capability,
            "target_service": target_service,
            "target_endpoint": target_endpoint,
            "message": (
                "This endpoint is no longer served by PAS. "
                f"Migrate to {target_service}:{target_endpoint}."
            ),
        },
    )
