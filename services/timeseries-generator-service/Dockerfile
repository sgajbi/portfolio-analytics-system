# Stage 1: Builder stage, using our new base image
FROM portfolio-analytics/python-base:latest as builder

# Set the Python path for the build context
ENV PYTHONPATH="/app/libs/portfolio-common:/app/services/timeseries-generator-service"

# Copy and install shared library
COPY libs/portfolio-common/ /app/libs/portfolio-common/
RUN pip install -e /app/libs/portfolio-common

# Copy the application and install it
COPY services/timeseries-generator-service/pyproject.toml /app/services/timeseries-generator-service/pyproject.toml
COPY services/timeseries-generator-service/app /app/services/timeseries-generator-service/app
RUN pip install /app/services/timeseries-generator-service

# Stage 2: Final production stage, also using our base image
FROM portfolio-analytics/python-base:latest

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy the application code and shared libs from the builder stage
COPY --from=builder --chown=appuser:appuser /app/services/timeseries-generator-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser

# Command to run the application
CMD ["python", "-m", "app.main"]