# src/services/timeseries-generator-service/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# NEW: Install curl for the healthcheck command
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && \
    chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder stage
FROM python-base as builder

ENV PYTHONPATH="/app/src/libs/portfolio-common:/app/src/services/timeseries-generator-service"

COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

COPY src/services/timeseries-generator-service/pyproject.toml /app/src/services/timeseries-generator-service/pyproject.toml
COPY src/services/timeseries-generator-service/app /app/src/services/timeseries-generator-service/app
RUN pip install /app/src/services/timeseries-generator-service

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/timeseries-generator-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs

USER appuser

# NEW: Expose port for health probes
EXPOSE 8085

CMD ["python", "-m", "app.main"]