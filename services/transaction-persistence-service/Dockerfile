# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim-bookworm as builder # CHANGED base image to Bookworm

WORKDIR /app

# Copy all necessary files for this service and shared libraries from the root build context.
# Paths are now relative to the project root.
COPY services/transaction-persistence-service/app /app/app
COPY services/transaction-persistence-service/requirements.txt /app/requirements.txt
COPY services/transaction-persistence-service/tests /app/tests
COPY services/transaction-persistence-service/startup.sh /app/startup.sh
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY libs/portfolio-common/ /app/libs/portfolio-common/

# Install application and test dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && pip install --no-cache-dir -r /app/tests/requirements.txt \
    && pip install -e /app/libs/portfolio-common

# Removed the dos2unix installation step as it's no longer needed with a newer base image
# and the assumption that startup.sh will have correct line endings in the repository.

# Set the Python path to include the service's app directory and the common libraries
ENV PYTHONPATH="/app:/app/libs/portfolio-common"

# Run tests
RUN pytest /app/tests

# Stage 2: Final production stage
FROM python:3.11-slim-bookworm # CHANGED base image to Bookworm

WORKDIR /app

# Copy built application code and necessary files from the builder stage
COPY --from=builder /app/app /app/app
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /app/startup.sh /app/startup.sh
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/libs/portfolio-common/ /app/libs/portfolio-common/

# Copy installed Python site-packages and executables
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Make startup script executable
RUN chmod +x /app/startup.sh

# Set the entrypoint to our startup script (overridden by docker-compose.yml 'command' for local development)
ENTRYPOINT ["/app/startup.sh"]