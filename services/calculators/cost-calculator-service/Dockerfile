# ----------- Stage 1: Builder stage -----------
FROM python:3.11-slim-bookworm as builder

WORKDIR /app

# Copy requirements files first for caching
COPY services/calculators/cost-calculator-service/requirements.txt /app/requirements.txt

# Copy shared libraries early to cache dependencies properly
COPY libs/portfolio-common/ /app/libs/portfolio-common/
COPY libs/financial-calculator-engine/ /app/libs/financial-calculator-engine/

# Create and activate virtual environment, then install dependencies including editable libs
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt && \
    /opt/venv/bin/pip install -e /app/libs/portfolio-common && \
    /opt/venv/bin/pip install -e /app/libs/financial-calculator-engine

# Copy application source code last for better cache usage
COPY services/calculators/cost-calculator-service/app /app/app

# Set environment variables for shared libs
ENV PYTHONPATH="/app:/app/libs/portfolio-common:/app/libs/financial-calculator-engine"

# ----------- Stage 2: Production stage -----------
FROM python:3.11-slim-bookworm

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy app and shared libs
COPY --from=builder /app/app /app/app
COPY --from=builder /app/libs/portfolio-common /app/libs/portfolio-common
COPY --from=builder /app/libs/financial-calculator-engine /app/libs/financial-calculator-engine

# Set environment variables for python
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/libs/portfolio-common:/app/libs/financial-calculator-engine"

# Expose default port if your app listens on a port (adjust if necessary)
EXPOSE 8000

# Create a non-root user and fix permissions
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /opt/venv /app

USER appuser

# Use production-ready command (adjust if you use Uvicorn or something else)
CMD ["python", "app/main.py"]