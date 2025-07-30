# Stage 1: Builder stage to install dependencies
FROM python:3.11-slim-bookworm as builder

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/libs/portfolio-common"

WORKDIR /app

# Create a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install shared library first for better layer caching
COPY libs/portfolio-common/ /app/libs/portfolio-common/
RUN pip install -e /app/libs/portfolio-common

# Copy the application and install its dependencies
COPY services/persistence-service/pyproject.toml /app/services/persistence-service/pyproject.toml
COPY services/persistence-service/app /app/services/persistence-service/app
RUN pip install /app/services/persistence-service

# Copy Alembic files (used by migration-runner)
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic


# Stage 2: Final production stage
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Create a non-root user for security
RUN useradd --create-home appuser

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy the application code and necessary package/Alembic files
COPY --from=builder --chown=appuser:appuser /app/services/persistence-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic


USER appuser

# Command to run the application using module-based execution
CMD ["python", "-m", "app.main"]