# libs/portfolio-common/portfolio_common/config.py
import os
from dotenv import load_dotenv

# Load environment variables from a .env file for local development.
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
MONGO_PORT = os.getenv("MONGO_PORT", "2717")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "portfolio_state")
MONGO_URL = f"mongodb://{MONGO_INITDB_ROOT_USERNAME}:{MONGO_INITDB_ROOT_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}"

# Kafka Configurations
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS_HOST") or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093")
KAFKA_RAW_PORTFOLIOS_TOPIC = os.getenv("KAFKA_RAW_PORTFOLIOS_TOPIC", "raw_portfolios")
KAFKA_RAW_TRANSACTIONS_TOPIC = os.getenv("KAFKA_RAW_TRANSACTIONS_TOPIC", "raw_transactions")
KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC = os.getenv("KAFKA_RAW_TRANSACTIONS_COMPLETED_TOPIC", "raw_transactions_completed")
KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC = os.getenv("KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC", "processed_transactions_completed")
KAFKA_INSTRUMENTS_TOPIC = os.getenv("KAFKA_INSTRUMENTS_TOPIC", "instruments")
KAFKA_MARKET_PRICES_TOPIC = os.getenv("KAFKA_MARKET_PRICES_TOPIC", "market_prices")
KAFKA_MARKET_PRICE_PERSISTED_TOPIC = os.getenv("KAFKA_MARKET_PRICE_PERSISTED_TOPIC", "market_price_persisted")
KAFKA_FX_RATES_TOPIC = os.getenv("KAFKA_FX_RATES_TOPIC", "fx_rates")
KAFKA_RAW_BUSINESS_DATES_TOPIC = os.getenv("KAFKA_RAW_BUSINESS_DATES_TOPIC", "raw_business_dates") # New Topic
KAFKA_PERSISTENCE_DLQ_TOPIC = os.getenv("KAFKA_PERSISTENCE_DLQ_TOPIC", "persistence_service.dlq")
KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC = os.getenv("KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC", "daily_position_snapshot_persisted")
KAFKA_POSITION_VALUED_TOPIC = os.getenv("KAFKA_POSITION_VALUED_TOPIC", "position_valued")
KAFKA_CASHFLOW_CALCULATED_TOPIC = os.getenv("KAFKA_CASHFLOW_CALCULATED_TOPIC", "cashflow_calculated")
KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC = os.getenv("KAFKA_POSITION_TIMESERIES_GENERATED_TOPIC", "position_timeseries_generated")
KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC = os.getenv("KAFKA_PORTFOLIO_TIMESERIES_GENERATED_TOPIC", "portfolio_timeseries_generated")
KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC = os.getenv("KAFKA_PORTFOLIO_AGGREGATION_REQUIRED_TOPIC", "portfolio_aggregation_required")
KAFKA_VALUATION_REQUIRED_TOPIC = os.getenv("KAFKA_VALUATION_REQUIRED_TOPIC", "valuation_required")
