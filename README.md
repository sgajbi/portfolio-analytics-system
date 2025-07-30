[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sgajbi/portfolio-analytics-system)

# Portfolio Analytics System

This system is a modular, event-driven platform designed to ingest financial data, perform complex calculations like cost basis, historical positions, and market valuation, and expose the results via a clean API. It uses a microservices architecture built with Python, FastAPI, Kafka, and PostgreSQL, all orchestrated with Docker Compose.
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
        RawData((raw_transactions, instruments, etc.));
        PersistenceCompleted((raw_transactions_completed, market_price_persisted));
        CostCalculated((processed_transactions_completed));
        PositionCalculated((position_history_persisted));
        CashflowCalculated((cashflow_calculated));
    end

    subgraph "Data Processing Pipeline"
        IngestionService -- Publishes --> RawData;
        RawData --> PersistenceService[persistence-service];
        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes --> PersistenceCompleted;

        PersistenceCompleted --> CostCalculator[cost-calculator-service];
        CostCalculator -- Updates --> DB;
        CostCalculator -- Publishes --> CostCalculated;
        
        PersistenceCompleted --> CashflowCalculator[cashflow-calculator-service];
        CashflowCalculator -- Writes --> DB;
        CashflowCalculator -- Publishes --> CashflowCalculated;

        CostCalculated --> PositionCalculator[position-calculator-service];
        PositionCalculator -- Writes --> DB;
        PositionCalculator -- Publishes --> PositionCalculated;
        PositionCalculated --> ValuationCalculator[position-valuation-calculator];
        PersistenceCompleted -- market_price_persisted --> ValuationCalculator;
        ValuationCalculator -- Updates --> DB;
    end

    subgraph "Data Query Path"
        QueryService -- Reads --> DB;
    end

-----

## 2\. Implemented Services

  * **`ingestion-service`**: A FastAPI application that serves as the write-only entry point for all incoming data (transactions, instruments, etc.). It validates data and publishes it to the appropriate "raw" Kafka topic.
  * **`query-service`**: A FastAPI application that serves as the read-only entry point for retrieving processed data. It queries the database to provide results for analytics and reporting.
  * **`persistence-service`**: A generic Kafka consumer that listens to all "raw" data topics. Its sole responsibility is to validate and persist incoming data to the PostgreSQL database.
  * **`cost-calculator-service`**: A Kafka consumer that listens for newly persisted transactions. It uses the `financial-calculator-engine` library to calculate cost basis (`net_cost`, `realized_gain_loss`) and publishes an enriched event.
  * **`cashflow-calculator-service`**: A Kafka consumer that listens for newly persisted transactions. It calculates a corresponding cashflow record based on configurable business rules and publishes an event upon persistence.
  * **`position-calculator-service`**: A Kafka consumer that listens for enriched transactions. It calculates and maintains a full, historical time series of portfolio positions and publishes an event upon persistence.
  * **`position-valuation-calculator`**: A Kafka consumer that listens for newly persisted positions and market prices. It calculates the market value and unrealized gain/loss for a position and saves it to the database.

-----

## 3\. Kafka Topics

  * **`raw_transactions`, `instruments`, `market_prices`, `fx_rates`**: Topics for raw, unprocessed data ingested by the system.
  * **`raw_transactions_completed`**: An event published by the `persistence-service` after a transaction has been successfully saved to the database.
  * **`market_price_persisted`**: An event published by the `persistence-service` after a market price has been saved.
  * **`processed_transactions_completed`**: An event published by the `cost-calculator-service` containing the transaction data enriched with calculated cost basis and gains/losses.
  * **`position_history_persisted`**: An event published by the `position-calculator-service` after a position history record has been saved to the database. This triggers the valuation service.
  * **`cashflow_calculated`**: An event published by the `cashflow-calculator-service` after a cashflow record has been calculated and saved to the database.

-----

## 4\. API Endpoints

### Write API (`ingestion-service` @ `http://localhost:8000`)

  * `POST /ingest/transactions`: Ingests a list of financial transactions.
  * `POST /ingest/instruments`: Ingests a list of financial instruments.
  * `POST /ingest/market-prices`: Ingests a list of market prices.
  * `POST /ingest/fx-rates`: Ingests a list of foreign exchange rates.
  * `GET /health`: Health check for the service.

### Read API (`query-service` @ `http://localhost:8001`)

  * `GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security held in a portfolio, including valuation data if available.
  * `GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions, each with its associated cashflow if one exists.
  * `GET /health`: Health check for the service.

-----

## 5\. Database Migrations (Alembic)

Database schema changes are managed by **Alembic**. When you change a SQLAlchemy model in `libs/portfolio-common/database_models.py`, you must generate a new migration script and apply it.

1.  **Ensure Postgres is Running**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration**: After changing a model, run this command. Alembic will compare your models to the database schema and create a new script in `allembic/versions/`.
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
│   ├── ingestion-service/    # The Write API
│   ├── query-service/          # The Read API
│   ├── persistence-service/    # Generic data persistence consumer
│   └── calculators/
│       ├── cost-calculator-service/ # Business logic for cost basis
│       ├── cashflow-calculator-service/ # Business logic for cashflows
│       ├── position-calculator-service/ # Business logic for positions
│       └── position-valuation-calculator/ # Business logic for valuation
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
    pip install -e libs/financial-calculator-engine \
            -e libs/portfolio-common \
            -e services/ingestion-service \
            -e services/persistence-service \
            -e services/calculators/cost-calculator-service \
            -e services/calculators/cashflow-calculator-service \
            -e services/calculators/position-calculator \
            -e services/calculators/position-valuation-calculator \
            -e services/query-service
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

5.  **Ingest a Market Price** to value the final position:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/market-prices' -H 'Content-Type: application/json' -d '{
    "market_prices": [{"securityId": "SEC_AAPL", "priceDate": "2025-07-25", "price": 180.0, "currency": "USD"}]
    }'
    ```

    Wait a few seconds for all services to process these events.

6.  **Query the Final Position**:
    Call the `query-service` to see the final state of your holding.

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/positions
    ```

    **Expected Response**: You will get a JSON response showing the final position of 60 shares, now including valuation details.

    ```json
    {
      "portfolio_id": "EXAMPLE_PORT_01",
      "positions": [
        {
          "security_id": "SEC_AAPL",
          "quantity": "60.0000000000",
          "cost_basis": "9000.0000000000",
          "instrument_name": "Apple Inc.",
          "position_date": "2025-07-25",
          "valuation": {
            "market_price": "180.0000000000",
            "market_value": "10800.0000000000",
            "unrealized_gain_loss": "1800.0000000000"
          }
        }
      ]
    }
    ```

7.  **Query Transactions with Cashflows**:
    Call the `query-service` to see the transaction details, including the calculated cashflow.

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/transactions
    ```

    **Expected Response**: You will see the transactions, with the `BUY` showing a negative (outgoing) cashflow and the `SELL` showing a positive (incoming) cashflow.

    ```json
    {
      "portfolio_id": "EXAMPLE_PORT_01",
      "total": 2,
      "skip": 0,
      "limit": 100,
      "transactions": [
        {
          "transaction_id": "EXAMPLE_SELL_01",
          "transaction_date": "2025-07-25T00:00:00",
          "transaction_type": "SELL",
          "security_id": "SEC_AAPL",
          "quantity": "40.0000000000",
          "price": "170.0000000000",
          "gross_transaction_amount": "6800.0000000000",
          "net_cost": "-6000.0000000000",
          "realized_gain_loss": "800.0000000000",
          "currency": "USD",
          "cashflow": {
            "amount": "6800.0000000000",
            "currency": "USD",
            "classification": "INVESTMENT_INFLOW",
            "timing": "EOD",
            "level": "POSITION",
            "calculationType": "NET"
          }
        },
        {
          "transaction_id": "EXAMPLE_BUY_01",
          "transaction_date": "2025-07-20T00:00:00",
          "transaction_type": "BUY",
          "security_id": "SEC_AAPL",
          "quantity": "100.0000000000",
          "price": "150.0000000000",
          "gross_transaction_amount": "15000.0000000000",
          "net_cost": "15000.0000000000",
          "realized_gain_loss": null,
          "currency": "USD",
          "cashflow": {
            "amount": "-15000.0000000000",
            "currency": "USD",
            "classification": "INVESTMENT_OUTFLOW",
            "timing": "EOD",
            "level": "POSITION",
            "calculationType": "NET"
          }
        }
      ]
    }
    ```

<!-- end list -->

 