FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the common module, requirements, and service-specific code
COPY common ./common
COPY services/transaction-cost-calculator-service/requirements.txt ./requirements.txt
COPY services/transaction-cost-calculator-service/app ./app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run the application
CMD ["python", "app/main.py"]