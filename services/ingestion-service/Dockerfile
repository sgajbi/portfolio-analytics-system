# Stage 1: Builder stage, using our new base image
FROM portfolio-analytics/python-base:latest as builder

# Set the Python path for the build context
ENV PYTHONPATH="/app/libs/portfolio-common:/app/services/ingestion-service"

# Install shared library first
COPY ./libs/portfolio-common /app/libs/portfolio-common
RUN pip install -e /app/libs/portfolio-common

# Copy the application and install its dependencies
COPY ./services/ingestion-service/pyproject.toml /app/services/ingestion-service/pyproject.toml
COPY ./services/ingestion-service/app /app/services/ingestion-service/app
RUN pip install /app/services/ingestion-service

# Copy and install test dependencies
COPY ./services/ingestion-service/tests/requirements.txt /app/tests/requirements.txt
RUN pip install --no-cache-dir -r /app/tests/requirements.txt

# Copy the rest of the test code
COPY ./services/ingestion-service/tests /app/tests

# Run tests to validate the build
RUN pytest /app/tests

# Stage 2: Final production stage, also using our base image
FROM portfolio-analytics/python-base:latest

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy only the necessary application code and shared libs from the builder stage
COPY --from=builder --chown=appuser:appuser /app/services/ingestion-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]