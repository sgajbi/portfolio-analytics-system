.PHONY: install lint typecheck test test-unit check docker-build clean

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

check: lint typecheck test

docker-build:
	docker build -f src/services/query_service/Dockerfile -t portfolio-analytics-query-service:ci .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; pathlib.Path('.coverage').unlink(missing_ok=True)"
