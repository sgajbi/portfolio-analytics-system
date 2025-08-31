# src/services/query_service/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder
FROM python-base as builder

# Shared libs for caching
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

COPY src/libs/performance-calculator-engine/ /app/src/libs/performance-calculator-engine/
RUN pip install /app/src/libs/performance-calculator-engine

COPY src/libs/risk-analytics-engine/ /app/src/libs/risk-analytics-engine/
RUN pip install /app/src/libs/risk-analytics-engine

# --- NEW: Install concentration-analytics-engine ---
COPY src/libs/concentration-analytics-engine/ /app/src/libs/concentration-analytics-engine/
RUN pip install /app/src/libs/concentration-analytics-engine
# --- END NEW ---

RUN pip install python-dateutil

# Copy service and install
COPY src/services/query_service/pyproject.toml /app/src/services/query_service/pyproject.toml
COPY src/services/query_service/app /app/src/services/query_service/app
RUN pip install /app/src/services/query_service

# Stage 3: Final
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/query_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs

USER appuser
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]