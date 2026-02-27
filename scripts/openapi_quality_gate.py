"""Enforce baseline OpenAPI quality for query-service endpoints."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

# Ensure the repository root is importable when script is executed directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
LIBS_ROOT = REPO_ROOT / "src" / "libs"
for lib_dir in LIBS_ROOT.glob("*"):
    if not lib_dir.is_dir():
        continue
    for candidate in (lib_dir, lib_dir / "src"):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))

ALLOWED_METHODS = {"get", "post", "put", "patch", "delete"}
EXEMPT_PATH_PREFIXES = ("/health/", "/metrics")


def is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


def _has_success_response(operation: dict) -> bool:
    responses = operation.get("responses", {})
    return any(code.startswith("2") for code in responses)


def _has_error_response(operation: dict) -> bool:
    responses = operation.get("responses", {})
    return any(
        code.startswith("4") or code.startswith("5") or code == "default" for code in responses
    )


def evaluate_schema(schema: dict) -> list[str]:
    errors: list[str] = []
    missing_docs: list[tuple[str, str, str]] = []
    operation_ids: list[str] = []

    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in ALLOWED_METHODS:
                continue

            method_upper = method.upper()
            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)

            if is_exempt(path):
                continue

            if not operation.get("summary"):
                missing_docs.append((method_upper, path, "summary"))
            if not operation.get("description"):
                missing_docs.append((method_upper, path, "description"))
            if not operation.get("tags"):
                missing_docs.append((method_upper, path, "tags"))

            if not operation.get("responses"):
                missing_docs.append((method_upper, path, "responses"))
            else:
                if not _has_success_response(operation):
                    missing_docs.append((method_upper, path, "2xx response"))
                if not _has_error_response(operation):
                    missing_docs.append((method_upper, path, "error response (4xx/5xx/default)"))

    if missing_docs:
        errors.append("OpenAPI quality gate: missing endpoint documentation/response contract")
        errors.extend(
            f"  - {method} {path}: missing {field_name}"
            for method, path, field_name in missing_docs
        )

    op_id_counts = Counter(operation_ids)
    duplicate_operation_ids = sorted([op_id for op_id, count in op_id_counts.items() if count > 1])
    if duplicate_operation_ids:
        errors.append("OpenAPI quality gate: duplicate operationId values")
        errors.extend(f"  - {op_id}" for op_id in duplicate_operation_ids)

    return errors


def main() -> int:
    from src.services.query_service.app.main import app

    schema = app.openapi()
    errors = evaluate_schema(schema)
    if errors:
        print("\n".join(errors))
        return 1

    print("OpenAPI quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
