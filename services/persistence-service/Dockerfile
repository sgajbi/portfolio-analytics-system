# Stage 1: Builder stage to install dependencies
FROM python:3.11-slim-bookworm as builder

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/libs/portfolio-common"

WORKDIR /app

# Copy dependency files and shared library first for better layer caching
COPY services/persistence-service/requirements.txt /app/requirements.txt
COPY libs/portfolio-common/ /app/libs/portfolio-common/

# Create a virtual environment and install dependencies
RUN python -m venv /opt/venv
RUN /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt && \
    /opt/venv/bin/pip install -e /app/libs/portfolio-common

# Copy the application source code and Alembic files
COPY services/persistence-service/app /app/app
COPY services/persistence-service/__init__.py /app/services/persistence-service/__init__.py
COPY services/__init__.py /app/services/__init__.py
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
COPY --from=builder --chown=appuser:appuser /app/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs
COPY --from=builder --chown=appuser:appuser /app/services /app/services
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic


USER appuser

# Command to run the application using module-based execution
CMD ["python", "-m", "app.main"]