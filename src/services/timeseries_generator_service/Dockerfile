# src/services/timeseries_generator_service/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm AS python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Utilities for healthchecks and basic ops
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create venv and non-root user
RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder
FROM python-base AS builder

# Pre-copy shared libs to leverage Docker layer caching
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

# Copy service sources (underscore paths) and install
COPY src/services/timeseries_generator_service/pyproject.toml /app/src/services/timeseries_generator_service/pyproject.toml
COPY src/services/timeseries_generator_service/app /app/src/services/timeseries_generator_service/app
RUN pip install /app/src/services/timeseries_generator_service

# Stage 3: Final
FROM python-base AS final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/timeseries_generator_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs

USER appuser
EXPOSE 8085
CMD ["python", "-m", "app.main"]
