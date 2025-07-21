# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim-bookworm as builder

WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY services/ingestion-service/requirements.txt /app/requirements.txt
COPY services/ingestion-service/tests/requirements.txt /app/tests/requirements.txt
COPY libs/portfolio-common/ /app/libs/portfolio-common/

# Install dependencies and shared libs first
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/tests/requirements.txt && \
    /opt/venv/bin/pip install -e /app/libs/portfolio-common

# Copy application source code last for better cache usage
COPY services/ingestion-service/app /app/app
COPY services/ingestion-service/tests /app/tests

# Set PYTHONPATH to locate your app and libs
ENV PYTHONPATH="/app:/app/libs/portfolio-common"

# Run tests to fail fast if any issues
RUN /opt/venv/bin/pytest /app/tests

# Stage 2: Production stage
FROM python:3.11-slim-bookworm

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy app and libs
COPY --from=builder /app/app /app/app
COPY --from=builder /app/libs/portfolio-common /app/libs/portfolio-common

# Set environment variables for python
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/libs/portfolio-common"

# Expose the port your app runs on
EXPOSE 8000

# Create non-root user and fix permissions
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /app /opt/venv

USER appuser

# Use Uvicorn with multiple workers for better concurrency in production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
