# Stage 1: Builder stage, using our new base image
FROM portfolio-analytics/python-base:latest as builder

# Set the Python path for the build context
ENV PYTHONPATH="/app/libs/portfolio-common:/app/libs/financial-calculator-engine:/app/services/calculators/cost-calculator-service"

# Copy and install shared libraries
COPY libs/portfolio-common/ /app/libs/portfolio-common/
COPY libs/financial-calculator-engine/ /app/libs/financial-calculator-engine/
RUN pip install -e /app/libs/portfolio-common && \
    pip install -e /app/libs/financial-calculator-engine

# Copy application and install it
COPY services/calculators/cost-calculator-service/pyproject.toml /app/services/calculators/cost-calculator-service/pyproject.toml
COPY services/calculators/cost-calculator-service/app /app/services/calculators/cost-calculator-service/app
RUN pip install /app/services/calculators/cost-calculator-service

# Stage 2: Final production stage, also using our base image
FROM portfolio-analytics/python-base:latest

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy the application code and shared libs from the builder stage
COPY --from=builder --chown=appuser:appuser /app/services/calculators/cost-calculator-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser

# Command to run the application
CMD ["python", "app/main.py"]