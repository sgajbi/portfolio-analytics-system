#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

echo "Migration Runner: Waiting for database connection..."
python -c '
import socket
import time
import os

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", 5432))
timeout = 45
start_time = time.time()

while time.time() - start_time < timeout:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("Migration Runner: Database is ready!")
            exit(0)
    except (socket.timeout, ConnectionRefusedError):
        print(f"Migration Runner: Database not ready yet, sleeping for 2 seconds...")
        time.sleep(2)

print("Migration Runner: Database did not become available in time.")
exit(1)
'

echo "Migration Runner: Running database migrations..."
python -m alembic upgrade head
echo "Migration Runner: Migrations completed successfully."