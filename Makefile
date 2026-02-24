.PHONY: install lint typecheck openapi-gate test test-unit test-integration-lite test-e2e-smoke security-audit check coverage-gate ci ci-local docker-build clean

install:
	python scripts/bootstrap_dev.py

lint:
	ruff check src/services/query_service/app tests/unit/services/query_service --ignore E501,E701,I001
	ruff format --check src/services/query_service/app tests/unit/services/query_service

typecheck:
	mypy --config-file mypy.ini

openapi-gate:
	python scripts/openapi_quality_gate.py

test:
	$(MAKE) test-unit

test-unit:
	python -m pytest tests/unit/services/query_service -q

test-integration-lite:
	python -m pytest tests/integration/services/query_service/test_capabilities_router_dependency.py tests/integration/services/query_service/test_concentration_router.py tests/integration/services/query_service/test_integration_router_dependency.py tests/integration/services/query_service/test_main_app.py tests/integration/services/query_service/test_performance_router.py tests/integration/services/query_service/test_portfolios_router_dependency.py tests/integration/services/query_service/test_position_analytics_router.py tests/integration/services/query_service/test_positions_router_dependency.py tests/integration/services/query_service/test_operations_router_dependency.py tests/integration/services/query_service/test_reference_data_routers.py tests/integration/services/query_service/test_lookup_contract_router.py tests/integration/services/query_service/test_review_router.py tests/integration/services/query_service/test_risk_router_dependency.py tests/integration/services/query_service/test_simulation_router_dependency.py tests/integration/services/query_service/test_summary_router.py tests/integration/services/query_service/test_transactions_router.py -q

test-e2e-smoke:
	python -m pytest tests/e2e/test_query_service_observability.py tests/e2e/test_complex_portfolio_lifecycle.py -q

security-audit:
	python -m pip_audit

check: lint typecheck openapi-gate test

coverage-gate:
	python scripts/coverage_gate.py

ci: lint typecheck test-integration-lite coverage-gate security-audit

ci-local: lint typecheck coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; pathlib.Path('.coverage').unlink(missing_ok=True)"
