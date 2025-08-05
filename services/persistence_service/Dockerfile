# services/persistence_service/Dockerfile

# Stage 1: Base image setup
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

ENV PYTHONPATH="/app/libs/portfolio-common:/app/services/persistence_service"

COPY ./libs/portfolio-common /app/libs/portfolio-common
RUN pip install -e /app/libs/portfolio-common

COPY ./services/persistence_service/pyproject.toml /app/services/persistence_service/pyproject.toml
COPY ./services/persistence_service/app /app/services/persistence_service/app
RUN pip install /app/services/persistence_service

COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY tools /app/tools

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/services/persistence_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/tools /app/tools

USER appuser

EXPOSE 8080

CMD ["python", "-m", "app.main"]