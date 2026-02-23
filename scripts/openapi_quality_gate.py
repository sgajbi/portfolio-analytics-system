"""Enforce baseline OpenAPI quality for query-service endpoints."""

from __future__ import annotations

from pathlib import Path
import sys
from collections import Counter

# Ensure the repository root is importable when script is executed directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.query_service.app.main import app


ALLOWED_METHODS = {"get", "post", "put", "patch", "delete"}
EXEMPT_PATH_PREFIXES = ("/health/",)


def is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


def main() -> int:
    schema = app.openapi()
    missing_docs: list[tuple[str, str, str]] = []
    operation_ids: list[str] = []

    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in ALLOWED_METHODS:
                continue

            operation_id = operation.get("operationId")
            if operation_id:
                operation_ids.append(operation_id)

            if is_exempt(path):
                continue

            if not operation.get("summary"):
                missing_docs.append((method.upper(), path, "summary"))
            if not operation.get("description"):
                missing_docs.append((method.upper(), path, "description"))

    op_id_counts = Counter(operation_ids)
    duplicate_operation_ids = sorted([op_id for op_id, count in op_id_counts.items() if count > 1])

    errors = 0
    if missing_docs:
        errors += 1
        print("OpenAPI quality gate: missing endpoint documentation")
        for method, path, field_name in missing_docs:
            print(f"  - {method} {path}: missing {field_name}")

    if duplicate_operation_ids:
        errors += 1
        print("OpenAPI quality gate: duplicate operationId values")
        for op_id in duplicate_operation_ids:
            print(f"  - {op_id}")

    if errors:
        return 1

    print("OpenAPI quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
