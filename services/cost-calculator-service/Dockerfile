# services/cost-calculator-service/Dockerfile
FROM python:3.11-slim-buster as builder

WORKDIR /app

# Copy all necessary files for this service and shared libraries from the root build context.
# Paths are now relative to the project root.
COPY services/cost-calculator-service/requirements.txt /app/requirements.txt
COPY services/cost-calculator-service/app /app/app
# No explicit tests folder found for cost-calculator-service in original Dockerfile or structure

# Copy shared libraries
COPY libs/portfolio-common/ /app/libs/portfolio-common/
COPY libs/financial-calculator-engine /app/libs/financial-calculator-engine

# Install Python dependencies, including the local editable libraries from requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Set PYTHONPATH to include the service's app directory and the common libraries
ENV PYTHONPATH="/app:/app/libs/portfolio-common:/app/libs/financial-calculator-engine"

# No tests to run in builder stage for this service as per original Dockerfile / project structure

# Stage 2: Final production stage
FROM python:3.11-slim-buster

WORKDIR /app

# Copy built application code and necessary files from the builder stage
COPY --from=builder /app/app /app/app
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /app/libs/portfolio-common/ /app/libs/portfolio-common/
COPY --from=builder /app/libs/financial-calculator-engine/ /app/libs/financial-calculator-engine/

# Copy installed Python site-packages and executables
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# The command to run the service will be defined in docker-compose.yml
CMD ["python", "app/main.py"]