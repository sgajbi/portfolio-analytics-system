.PHONY: install lint typecheck test test-unit test-integration-lite check coverage-gate ci-local docker-build clean

install:
	python scripts/bootstrap_dev.py

lint:
	ruff check src/services/query_service/app tests/unit/services/query_service --ignore E501,E701,I001
	ruff format --check src/services/query_service/app tests/unit/services/query_service

typecheck:
	mypy --config-file mypy.ini

test:
	$(MAKE) test-unit

test-unit:
	python -m pytest tests/unit/services/query_service -q

test-integration-lite:
	python -m pytest tests/integration/services/query_service/test_concentration_router.py tests/integration/services/query_service/test_position_analytics_router.py tests/integration/services/query_service/test_review_router.py tests/integration/services/query_service/test_summary_router.py tests/integration/services/query_service/test_performance_router.py tests/integration/services/query_service/test_risk_router_dependency.py tests/integration/services/query_service/test_operations_router_dependency.py -q

check: lint typecheck test

coverage-gate:
	python scripts/coverage_gate.py

ci-local: lint typecheck coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; pathlib.Path('.coverage').unlink(missing_ok=True)"
