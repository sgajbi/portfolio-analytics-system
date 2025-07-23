#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# 1. Wait for the database to be ready
echo "Waiting for database connection..."
python -c '
import socket
import time
import os

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", 5432))
timeout = 30
start_time = time.time()

while time.time() - start_time < timeout:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("Database is ready!")
            exit(0)
    except (socket.timeout, ConnectionRefusedError):
        print(f"Database not ready yet, sleeping for 2 seconds...")
        time.sleep(2)

print("Database did not become available in time.")
exit(1)
'

# 2. Run database migrations
echo "Running database migrations..."
# CORRECTED: Run alembic as a Python module for more reliable pathing
python -m alembic upgrade head

# 3. Start the main application
echo "Starting Transaction Persistence Service application..."
exec python app/main.py