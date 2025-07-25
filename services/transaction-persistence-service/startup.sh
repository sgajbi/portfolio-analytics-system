#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# Read the first argument passed to the script. Default to "run" if not provided.
COMMAND=${1:-run}

# --- Shared function to wait for the database ---
wait_for_db() {
  echo "Waiting for database connection..."
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
            print("Database is ready!")
            exit(0)
    except (socket.timeout, ConnectionRefusedError):
        print(f"Database not ready yet, sleeping for 2 seconds...")
        time.sleep(2)

print("Database did not become available in time.")
exit(1)
'
}

# --- Main execution logic ---
if [ "$COMMAND" = "migrate" ]; then
  echo "Running in MIGRATE mode..."
  wait_for_db
  echo "Running database migrations..."
  python -m alembic upgrade head
  echo "Migrations completed successfully."

elif [ "$COMMAND" = "run" ]; then
  echo "Running in RUN mode..."
  wait_for_db
  echo "Starting Transaction Persistence Service application..."
  exec python app/main.py

else
  echo "Error: Unknown command '$COMMAND'"
  exit 1
fi