# services/cost-calculator-service/Dockerfile
FROM python:3.11-slim-buster

WORKDIR /app

# Copy the requirements file first to leverage Docker layer caching
COPY ./services/cost-calculator-service/requirements.txt /app/requirements.txt

# Copy the shared common module and the calculator engine library
COPY ./common /app/common
COPY ./libs/financial-calculator-engine /app/libs/financial-calculator-engine

# Install Python dependencies, including the local library
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application code into the container
COPY ./services/cost-calculator-service/app /app/app

# Set PYTHONPATH to include the library's source
ENV PYTHONPATH="/app:/app/libs/financial-calculator-engine/src"

# The command to run the service will be defined in docker-compose.yml
CMD ["python", "app/main.py"]