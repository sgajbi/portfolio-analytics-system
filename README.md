
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sgajbi/portfolio-analytics-system)

# Portfolio Analytics System

This system is a modular, event-driven platform designed to ingest financial data, perform complex calculations like cost basis and historical positions, and expose the results via a clean API. It uses a microservices architecture built with Python, FastAPI, Kafka, and PostgreSQL, all orchestrated with Docker Compose.

---
## Table of Contents

1.  [System Architecture](#1-system-architecture)
2.  [Implemented Services](#2-implemented-services)
3.  [Kafka Topics](#3-kafka-topics)
4.  [API Endpoints](#4-api-endpoints)
5.  [Database Migrations (Alembic)](#5-database-migrations-alembic)
6.  [Directory Structure](#6-directory-structure)
7.  [Local Development Setup](#7-local-development-setup)
8.  [Testing](#8-testing)
9.  [Full Usage Example](#9-full-usage-example)

---
## 1. System Architecture

The system is designed around a central Kafka message bus to ensure services are decoupled and can be scaled independently. Data flows through a pipeline of services, where it is persisted, enriched, and calculated. A dedicated query service provides read access to the processed data.

```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        User[User/Client] -- POST Data --> IngestionService[ingestion-service:8000];
        User -- GET Data --> QueryService[query-service:8001];
    end

    subgraph "Kafka Topics"
        RawTransactions((raw_transactions));
        RawCompleted((raw_transactions_completed));
        ProcessedCompleted((processed_transactions_completed));
        OtherRawData((instruments, fx_rates, etc.));
    end

    subgraph "Data Processing Pipeline"
        IngestionService -- Publishes --> RawTransactions;
        IngestionService -- Publishes --> OtherRawData;

        RawTransactions --> PersistenceService[persistence-service];
        OtherRawData --> PersistenceService;

        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes --> RawCompleted;

        RawCompleted --> CostCalculator[cost-calculator-service];
        CostCalculator -- Updates --> DB;
        CostCalculator -- Publishes --> ProcessedCompleted;

        ProcessedCompleted --> PositionCalculator[position-calculator-service];
        PositionCalculator -- Writes --> DB;
    end

    subgraph "Data Query Path"
        QueryService -- Reads --> DB;
    end
````

-----

## 2\. Implemented Services

  * **`ingestion-service`**: A FastAPI application that serves as the write-only entry point for all incoming data (transactions, instruments, etc.). It validates data and publishes it to the appropriate "raw" Kafka topic.
  * **`query-service`**: A FastAPI application that serves as the read-only entry point for retrieving processed data. It queries the database to provide results for analytics and reporting.
  * **`persistence-service`**: A generic Kafka consumer that listens to all "raw" data topics. Its sole responsibility is to validate and persist incoming data to the PostgreSQL database.
  * **`cost-calculator-service`**: A Kafka consumer that listens for newly persisted transactions. It uses the `financial-calculator-engine` library to calculate cost basis (`net_cost`, `realized_gain_loss`) and publishes an enriched event.
  * **`position-calculator-service`**: A Kafka consumer that listens for enriched transactions. It calculates and maintains a full, historical time series of portfolio positions, correctly handling backdated transactions.

-----

## 3\. Kafka Topics

  * **`raw_transactions`, `instruments`, `market_prices`, `fx_rates`**: Topics for raw, unprocessed data ingested by the system.
  * **`raw_transactions_completed`**: An event published by the `persistence-service` after a transaction has been successfully saved to the database.
  * **`processed_transactions_completed`**: An event published by the `cost-calculator-service` containing the transaction data enriched with calculated cost basis and gains/losses.

-----

## 4\. API Endpoints

### Write API (`ingestion-service` @ `http://localhost:8000`)

  * `POST /ingest/transactions`: Ingests a list of financial transactions.
  * `POST /ingest/instruments`: Ingests a list of financial instruments.
  * `POST /ingest/market-prices`: Ingests a list of market prices.
  * `POST /ingest/fx-rates`: Ingests a list of foreign exchange rates.
  * `GET /health`: Health check for the service.

### Read API (`query-service` @ `http://localhost:8001`)

  * `GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security held in a portfolio.
  * `GET /health`: Health check for the service.

-----

## 5\. Database Migrations (Alembic)

Database schema changes are managed by **Alembic**. When you change a SQLAlchemy model in `libs/portfolio-common/database_models.py`, you must generate a new migration script and apply it.

1.  **Ensure Postgres is Running**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration**: After changing a model, run this command. Alembic will compare your models to the database schema and create a new script in `alembic/versions/`.
    ```bash
    alembic revision --autogenerate -m "a descriptive message for your change"
    ```
3.  **Apply the Migration**: This command applies all pending migration scripts to the database.
    ```bash
    alembic upgrade head
    ```

-----

## 6\. Directory Structure

The project is organized as a monorepo with shared libraries and distinct microservices.

```
sgajbi-portfolio-analytics-system/
├── alembic/                  # Database migration scripts
├── libs/                     # Shared Python libraries
│   ├── portfolio-common/     # Common DB models, events, and utilities
│   └── financial-calculator-engine/ # Core financial calculation logic
├── services/                 # Individual microservices
│   ├── ingestion-service/      # The Write API
│   ├── query-service/          # The Read API
│   ├── persistence-service/    # Generic data persistence consumer
│   ├── cost-calculator-service/ # Business logic for cost basis
│   └── calculators/
│       └── position-calculator-service/ # Business logic for positions
├── tests/
│   └── e2e/                    # End-to-end tests for the whole system
├── docker-compose.yml        # Orchestrates all services for local development
└── README.md                 # This file
```

-----

## 7\. Local Development Setup

### Prerequisites

  * **Docker Desktop**: Ensure it's installed and running.
  * **Python 3.11**: You must have a Python 3.11 interpreter installed locally.

### Initial Setup

1.  **Clone & Navigate**: `git clone <repo-url> && cd portfolio-analytics-system`
2.  **Create `.env` file**: `cp .env.example .env`
3.  **Create & Activate Venv**:
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
4.  **Install All Dependencies**:
    ```bash
    pip install -e libs/financial-calculator-engine -e libs/portfolio-common
    pip install -r services/ingestion-service/requirements.txt \
                -r services/persistence-service/requirements.txt \
                -r services/cost-calculator-service/requirements.txt \
                -r services/calculators/position-calculator/requirements.txt \
                -r services/query-service/requirements.txt
    ```

### Running the System

```bash
# To start all services
docker compose up --build -d

# To check the status of services
docker compose ps

# To stop all services
docker compose down -v
```

-----

## 8\. Testing

### End-to-End Tests

The project includes a suite of end-to-end tests that orchestrate the entire Docker environment to validate the full pipeline.

1.  **Install Test Dependencies**:
    ```bash
    pip install -r tests/e2e/requirements.txt
    ```
2.  **Run Tests**:
    ```bash
    pytest tests/e2e/
    ```

-----

## 9\. Full Usage Example

This example demonstrates the full flow from ingestion to querying the final calculated position.

1.  **Start the entire system**:

    ```bash
    docker compose up --build -d
    ```

    Wait about a minute for all services to become healthy.

2.  **Ingest an Instrument** (e.g., Apple Inc.):

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/instruments' -H 'Content-Type: application/json' -d '{
    "instruments": [{"securityId": "SEC_AAPL", "name": "Apple Inc.", "isin": "US0378331005", "instrumentCurrency": "USD", "productType": "Equity"}]
    }'
    ```

3.  **Ingest a BUY Transaction**:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/transactions' -H 'Content-Type: application/json' -d '{
    "transactions": [{"transaction_id": "EXAMPLE_BUY_01", "portfolio_id": "EXAMPLE_PORT_01", "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-07-20", "transaction_type": "BUY", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"}]
    }'
    ```

4.  **Ingest a SELL Transaction**:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/transactions' -H 'Content-type: application/json' -d '{
    "transactions": [{"transaction_id": "EXAMPLE_SELL_01", "portfolio_id": "EXAMPLE_PORT_01", "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-07-25", "transaction_type": "SELL", "quantity": 40, "price": 170, "gross_transaction_amount": 6800, "trade_currency": "USD", "currency": "USD"}]
    }'
    ```

    Wait a few seconds for all services to process these events.

5.  **Query the Final Position**:
    Call the `query-service` to see the final state of your holding.

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/positions
    ```

    **Expected Response**: You will get a JSON response showing the final position of 60 shares with its corresponding average cost basis.

    ```json
    {
      "portfolio_id": "EXAMPLE_PORT_01",
      "positions": [
        {
          "security_id": "SEC_AAPL",
          "quantity": "60.0000000000",
          "cost_basis": "9000.0000000000",
          "instrument_name": "Apple Inc.",
          "position_date": "2025-07-25"
        }
      ]
    }
    ```

<!-- end list -->
 