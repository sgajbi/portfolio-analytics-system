
FROM python:3.11-slim-buster

# Set the working directory inside the container
WORKDIR /app

# Copy the common module, service-specific app, and requirements file
COPY ./common /app/common
COPY ./services/transaction-cost-calculator-service/app /app/app
COPY ./services/transaction-cost-calculator-service/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Set PYTHONPATH to ensure modules are found
ENV PYTHONPATH="/app"

# Command to run the application (can be overridden by docker-compose)
CMD ["python", "app/main.py"]