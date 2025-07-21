# Stage 1: Builder stage with test dependencies
FROM python:3.11-slim-buster as builder

WORKDIR /app

# Copy all application and test files
COPY ./services/transaction-persistence-service/ /app/
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
FROM python:3.11-slim-buster

WORKDIR /app

# Copy application files and startup script from the builder stage
COPY --from=builder /app/app /app/app
COPY --from=builder /app/requirements.txt /app/requirements.txt
COPY --from=builder /app/startup.sh /app/startup.sh

# Copy installed libraries and executables
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Make startup script executable
RUN chmod +x /app/startup.sh

# Set the entrypoint to our startup script
ENTRYPOINT ["/app/startup.sh"]