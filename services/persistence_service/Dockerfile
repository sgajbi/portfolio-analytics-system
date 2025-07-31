# services/persistence_service/Dockerfile
# Stage 1: Builder stage, using our new base image
FROM portfolio-analytics/python-base:latest as builder

# Set the Python path for the build context
# CORRECTED PATH
ENV PYTHONPATH="/app/libs/portfolio-common:/app/services/persistence_service"

# Install shared library first
COPY ./libs/portfolio-common /app/libs/portfolio-common
RUN pip install -e /app/libs/portfolio-common

# Copy the application and install its dependencies
# CORRECTED PATHS
COPY ./services/persistence_service/pyproject.toml /app/services/persistence_service/pyproject.toml
COPY ./services/persistence_service/app /app/services/persistence_service/app
RUN pip install /app/services/persistence_service

# Copy Alembic files (used by migration-runner)
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

# Stage 2: Final production stage, also using our base image
FROM portfolio-analytics/python-base:latest

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy only the necessary application code, shared libs, and Alembic files
# CORRECTED PATH
COPY --from=builder --chown=appuser:appuser /app/services/persistence_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic

USER appuser

# Command to run the application
CMD ["python", "-m", "app.main"]