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

# Copy and install shared library first for better layer caching
COPY libs/portfolio-common/ /app/libs/portfolio-common/
RUN pip install -e /app/libs/portfolio-common

# Copy the application and install its dependencies
COPY services/timeseries-generator-service/pyproject.toml /app/services/timeseries-generator-service/pyproject.toml
COPY services/timeseries-generator-service/app /app/services/timeseries-generator-service/app
RUN pip install /app/services/timeseries-generator-service

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

# Copy the application code
COPY --from=builder --chown=appuser:appuser /app/services/timeseries-generator-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser

CMD ["python", "-m", "app.main"]