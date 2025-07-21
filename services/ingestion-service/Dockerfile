# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Copy all necessary files for this service and shared libraries from the root build context.
# Paths are now relative to the project root.
COPY services/ingestion-service/app /app/app
COPY services/ingestion-service/requirements.txt /app/requirements.txt
COPY services/ingestion-service/tests /app/tests
COPY libs/portfolio-common/ /app/libs/portfolio-common/

# Install application and test dependencies
# The requirements.txt is now correctly located at /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -r /app/tests/requirements.txt \
    && pip install -e /app/libs/portfolio-common

# Set the Python path to include the service's app directory and the common libraries
ENV PYTHONPATH="/app:/app/libs/portfolio-common"

# Run tests
RUN pytest /app/tests

# Stage 2: Final production stage
FROM python:3.11-slim

WORKDIR /app

# Copy built application code and necessary files from the builder stage
COPY --from=builder /app/app /app/app
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /app/libs/portfolio-common/ /app/libs/portfolio-common/

# Copy installed Python site-packages and executables
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn (overridden by docker-compose.yml 'command' for local development)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]