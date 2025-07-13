

FROM python:3.11-slim

WORKDIR /app

# Copy common module first as it's a dependency for all services
COPY ./common /app/common

# Copy service specific files
COPY ./services/transaction-persistence-service/app /app/app
COPY ./services/transaction-persistence-service/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Command to run the application (placeholder for now)
CMD ["python", "app/main.py"]