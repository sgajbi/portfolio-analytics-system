# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Copy all application and test files
COPY ./services/ingestion-service/ /app/
COPY ./libs/portfolio-common/ /app/libs/portfolio-common/

# Install application and test dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -r /app/tests/requirements.txt \
    && pip install -e /app/libs/portfolio-common

# Set the Python path
ENV PYTHONPATH="/app"

# Run tests
RUN pytest /app/tests

# Stage 2: Final production stage
FROM python:3.11-slim

WORKDIR /app

# Copy only the application files from the builder stage
COPY --from=builder /app/app /app/app
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/

# Install application dependencies (already copied from builder)
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]