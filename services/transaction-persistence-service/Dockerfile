# services/transaction-persistence-service/Dockerfile
FROM python:3.11-slim-buster

WORKDIR /app

# COPY common /app/common <-- THIS LINE HAS BEEN REMOVED
COPY services/transaction-persistence-service/app /app/app
COPY services/transaction-persistence-service/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the startup script and make it executable
COPY services/transaction-persistence-service/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Set the entrypoint to our new script
ENTRYPOINT ["/app/startup.sh"]