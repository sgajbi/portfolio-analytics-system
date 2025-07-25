import os
from dotenv import load_dotenv

# Load environment variables from a .env file for local development.
# This line will be ignored if run inside a Docker container where an .env file doesn't exist.
load_dotenv()


# Database Configurations
POSTGRES_USER = os.getenv("POSTGRES_USER", "user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_DB = os.getenv("POSTGRES_DB", "portfolio_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

MONGO_INITDB_ROOT_USERNAME = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
MONGO_INITDB_ROOT_PASSWORD = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "portfolio_state")
MONGO_URL = f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}"

# Kafka Configurations
# When running in Docker, the value is supplied by docker-compose.
# When running locally, this will now be loaded from the .env file.
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093")
KAFKA_RAW_TRANSACTIONS_TOPIC = os.getenv("KAFKA_RAW_TRANSACTIONS_TOPIC", "raw_transactions")
KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC = os.getenv("KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC", "raw_transactions_completed")
KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC = os.getenv("KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC", "processed_transactions_completed")
KAFKA_INSTRUMENTS_TOPIC = os.getenv("KAFKA_INSTRUMENTS_TOPIC", "instruments")
KAFKA_MARKET_PRICES_TOPIC = os.getenv("KAFKA_MARKET_PRICES_TOPIC", "market_prices")
KAFKA_FX_RATES_TOPIC = os.getenv("KAFKA_FX_RATES_TOPIC", "fx_rates")