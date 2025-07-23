# services/ingestion-service/Dockerfile

# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim-buster as builder

WORKDIR /app

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install test dependencies first
COPY ./services/ingestion-service/tests/requirements.txt /app/tests/requirements.txt
RUN pip install --no-cache-dir -r /app/tests/requirements.txt

# Install application dependencies, including the shared library
COPY ./services/ingestion-service/requirements.txt /app/requirements.txt
COPY ./libs/portfolio-common /app/libs/portfolio-common
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install -e /app/libs/portfolio-common

# Copy the rest of the application and test code
COPY ./services/ingestion-service/app /app/app
COPY ./services/ingestion-service/tests /app/tests

# ==================== TEMPORARY DIAGNOSTIC STEP ====================
# This will print the contents of the test file during the build.
RUN echo "--- Verifying test_transaction_model.py content ---" && \
    cat /app/tests/unit/test_transaction_model.py && \
    echo "-------------------------------------------------"
# ===================================================================

# Set the Python path so imports from 'app' work correctly
ENV PYTHONPATH="/app"

# Run tests to validate the build
RUN pytest /app/tests

# Stage 2: Final production stage
FROM python:3.11-slim-buster

WORKDIR /app

# Create a non-root user for security
RUN useradd --create-home appuser
USER appuser

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy the application code from the builder stage
COPY --from=builder --chown=appuser:appuser /app/app /app/app

# Set the PATH to include the venv
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]