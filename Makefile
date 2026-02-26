.PHONY: install lint typecheck monetary-float-guard openapi-gate migration-smoke migration-apply test test-unit test-integration-lite test-e2e-smoke security-audit check coverage-gate ci ci-local docker-build clean

install:
	python scripts/bootstrap_dev.py

lint:
	ruff check src/services/query_service/app tests/unit/services/query_service --ignore E501,E701,I001
	ruff format --check src/services/query_service/app tests/unit/services/query_service
	$(MAKE) monetary-float-guard

monetary-float-guard:
	python scripts/check_monetary_float_usage.py

typecheck:
	mypy --config-file mypy.ini

openapi-gate:
	python scripts/openapi_quality_gate.py

migration-smoke:
	python scripts/migration_contract_check.py --mode alembic-sql

migration-apply:
	alembic upgrade head

test:
	$(MAKE) test-unit

test-unit:
	python scripts/test_manifest.py --suite unit --quiet

test-integration-lite:
	python scripts/test_manifest.py --suite integration-lite --quiet

test-e2e-smoke:
	python scripts/test_manifest.py --suite e2e-smoke --quiet

security-audit:
	python -m pip_audit -r tests/requirements.txt

check: lint typecheck openapi-gate test

coverage-gate:
	python scripts/coverage_gate.py

ci: lint typecheck openapi-gate migration-smoke test-integration-lite coverage-gate security-audit

ci-local: lint typecheck coverage-gate

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; pathlib.Path('.coverage').unlink(missing_ok=True)"
