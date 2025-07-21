# ----------- Stage 1: Builder with dependencies and tests -----------
FROM python:3.11-slim-bookworm AS builder

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/libs/portfolio-common"

WORKDIR /app

# Install system dependencies for building and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy all needed files
COPY services/transaction-persistence-service/app /app/app
COPY services/transaction-persistence-service/tests /app/tests
COPY services/transaction-persistence-service/requirements.txt /app/requirements.txt
COPY services/transaction-persistence-service/startup.sh /app/startup.sh
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY libs/portfolio-common/ /app/libs/portfolio-common/

# Fix Windows line endings in shell scripts
RUN sed -i 's/\r$//' /app/startup.sh

# Create a virtual environment for dependencies
RUN python -m venv /opt/venv

# Activate virtualenv and install dependencies as root so /opt/venv has correct permissions
RUN /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/tests/requirements.txt && \
    /opt/venv/bin/pip install -e /app/libs/portfolio-common

# Run tests with the virtualenv activated
RUN /opt/venv/bin/pytest /app/tests

# ----------- Stage 2: Final minimal runtime -----------
FROM python:3.11-slim-bookworm AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/libs/portfolio-common" \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code and configs
COPY --from=builder /app/app /app/app
COPY --from=builder /app/startup.sh /app/startup.sh
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/libs/portfolio-common/ /app/libs/portfolio-common/

# Make sure startup script is executable
RUN chmod +x /app/startup.sh

# Create a non-root user with proper permissions to /opt/venv and app folders
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /opt/venv /app

USER appuser

ENTRYPOINT ["/app/startup.sh"]
