# services/transaction-persistence-service/Dockerfile

# Use a specific Python base image for consistency and stability
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the common package first as it's a dependency for app
COPY common /app/common

# Copy the application code into the container
COPY services/transaction-persistence-service/app /app/app

# Copy the requirements file
COPY services/transaction-persistence-service/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# NEW: Copy the startup script and make it executable
COPY services/transaction-persistence-service/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# The command to run the service will be defined in docker-compose.yml,
# which will now execute the startup.sh script.