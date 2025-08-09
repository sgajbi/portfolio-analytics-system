# services/ingestion-service/Dockerfile

# Stage 1: Base image setup. This replaces the dependency on a pre-built image.
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && \
    chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder stage
FROM python-base as builder

ENV PYTHONPATH="/app/libs/portfolio-common:/app/services/ingestion-service"

COPY ./libs/portfolio-common /app/libs/portfolio-common
RUN pip install -e /app/libs/portfolio-common

COPY ./services/ingestion-service/pyproject.toml /app/services/ingestion-service/pyproject.toml
COPY ./services/ingestion-service/app /app/services/ingestion-service/app
RUN pip install /app/services/ingestion-service

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/services/ingestion-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]