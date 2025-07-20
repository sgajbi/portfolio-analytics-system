#!/bin/bash
set -e

# --- Debugging Environment Variables (removed) ---
# echo "--- Environment Variables ---"
# echo "POSTGRES_USER: ${POSTGRES_USER}"
# echo "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}"
# echo "POSTGRES_HOST: ${POSTGRES_HOST}"
# echo "POSTGRES_DB: ${POSTGRES_DB}"
# echo "DATABASE_URL: ${DATABASE_URL}"
# echo "-----------------------------"

# --- Wait for PostgreSQL to be ready ---
echo "Waiting for PostgreSQL to be ready..."
python -c '
import sys, time, os
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("DATABASE_URL environment variable is not set in Python.", file=sys.stderr)
    sys.exit(1)
engine = create_engine(db_url)
for i in range(20): # Retry up to 20 times, 1 second apart
    try:
        conn = engine.connect()
        conn.close()
        print("PostgreSQL is ready!")
        break
    except OperationalError:
        print(f"PostgreSQL not ready, retrying... ({i+1}/20)")
        time.sleep(1)
else:
    print("PostgreSQL did not become ready in time. Exiting.", file=sys.stderr)
    sys.exit(1)
'

echo "PostgreSQL is ready, proceeding with migrations."

# --- Run Alembic Migrations ---
# NEW: Added --verbose flag to see full Alembic output
alembic -c /app/alembic.ini upgrade head --verbose

echo "Alembic migrations applied."

# --- Start the main application ---
echo "Starting Transaction Persistence Service application..."
exec python app/main.py