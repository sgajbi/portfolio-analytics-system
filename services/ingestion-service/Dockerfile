FROM python:3.11-slim

WORKDIR /app

# Copy common module first as it's a dependency
COPY ./common /app/common

# Copy ingestion service specific files
COPY ./services/ingestion-service/app /app/app
COPY ./services/ingestion-service/requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]