from __future__ import annotations

from pathlib import Path

from scripts.test_manifest import SUITES, get_suite, validate_suite_paths


def test_integration_lite_suite_includes_lookup_contract_router() -> None:
    integration_suite = get_suite("integration-lite")
    assert (
        "tests/integration/services/query_service/test_lookup_contract_router.py"
        in integration_suite
    )


def test_manifest_paths_exist_for_all_suites() -> None:
    for suite_name in SUITES:
        validate_suite_paths(suite_name)
        for path in get_suite(suite_name):
            assert Path(path).exists()
