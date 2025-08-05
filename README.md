[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sgajbi/portfolio-analytics-system)
 
# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

An event-driven, microservices-based platform for comprehensive portfolio analytics. Designed for wealth management, this system ingests financial data, performs complex calculations (cost basis, positions, valuation), and exposes the results through a clean, scalable API.
---
## Table of Contents

1.  [System Architecture](#1-system-architecture)
2.  [Core Services](#2-core-services)
3.  [Data Flow & Kafka Topics](#3-data-flow--kafka-topics)
4.  [API Endpoints](#4-api-endpoints)
5.  [Observability](#5-observability)
6.  [Local Development](#6-local-development)
7.  [Testing](#7-testing)
8.  [Database Migrations](#8-database-migrations)
9.  [Directory Structure](#9-directory-structure)

---
## 1. System Architecture

The system is architected around a central **Apache Kafka** message bus, promoting a highly decoupled and scalable environment. Data flows through a choreographed pipeline of specialized microservices, each responsible for a distinct business capability. Raw data is ingested, persisted, enriched through a series of calculations, and finally made available for query.

### 1.1 Startup Sequence & Reliability

To guarantee data integrity and prevent errors during startup, the system employs a strict, automated startup sequence.

#### Topic Creation
On startup, a dedicated `kafka-topic-creator` service runs first. It connects to Kafka and idempotently creates every topic required by the entire platform, ensuring they are configured with production-ready settings (e.g., replication factor, retention). All other services explicitly depend on the successful completion of this service.

#### Service Health Checks
Before any consumer service begins polling for messages, it performs a startup health check. It connects to the Kafka AdminClient and verifies that all of the topics it needs to subscribe to already exist. The service will retry this check for up to 60 seconds. If the topics do not appear, the service will exit with a critical error, preventing it from running in an invalid state.

#### Idempotent Processing
To ensure data consistency and prevent duplicate calculations from event replays, all calculator services are **idempotent**. This is achieved by:
1.  Generating a unique ID for each incoming Kafka message (from its topic, partition, and offset).
2.  Using a shared `processed_events` table in the database.
3.  Wrapping the business logic in an atomic transaction: the service first checks if the event ID exists in the table. If not, it processes the data, saves the results, and inserts the event ID into the table as a single, atomic operation.
4.  If the event ID already exists, the entire operation is skipped.

```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        Client[User/Client] -- POST Data --> IngestionService[ingestion-service:8000];
        Client -- GET Data --> QueryService[query-service:8001];
    end

    subgraph "Kafka Message Bus"
        RawData((raw_events));
        PersistenceCompleted((persistence_completed));
        CalculationsCompleted((calculations_completed));
    end

    subgraph "Data Processing Pipeline"
        IngestionService -- Publishes --> RawData;
        RawData --> PersistenceService[persistence-service];
        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes --> PersistenceCompleted;

        PersistenceCompleted -- "raw_transactions_completed" --> CostCalculator[cost-calculator-service];
        CostCalculator -- Updates --> DB;
        CostCalculator -- Publishes --> CalculationsCompleted;
        
        PersistenceCompleted -- "raw_transactions_completed" --> CashflowCalculator[cashflow-calculator-service];
        CashflowCalculator -- Writes --> DB;
        CalculationsCompleted -- "processed_transactions_completed" --> PositionCalculator[position-calculator-service];
        PositionCalculator -- Writes --> DB;
        PositionCalculator -- Publishes --> CalculationsCompleted;

        CalculationsCompleted -- "position_history_persisted" --> ValuationCalculator[position-valuation-calculator];
        PersistenceCompleted -- "market_price_persisted" --> ValuationCalculator;
        ValuationCalculator -- Updates --> DB;
    end

    subgraph "Data Query Layer"
        QueryService -- Reads --> DB;
    end
````

## 2\. Core Services

  - **`ingestion-service`**: A write-only FastAPI application serving as the single entry point for all incoming data (portfolios, instruments, transactions, etc.). It validates and publishes raw events to Kafka.
  - **`persistence-service`**: A generic consumer responsible for persisting raw data from Kafka to the PostgreSQL database. On successful persistence, it publishes a `_completed` event.
  - **`query-service`**: A read-only FastAPI application providing access to all processed and calculated data for reporting and analytics.
  - **Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic:
      - **`cost-calculator-service`**: Calculates cost basis, realized gains/losses for transactions.
      - **`cashflow-calculator-service`**: Generates cashflow records from transactions.
      - **`position-calculator-service`**: Computes and maintains a historical time series of portfolio positions.
      - **`position-valuation-calculator`**: Calculates the market value and unrealized gain/loss of positions using the latest market prices.
      - **`timeseries-generator-service`**: Consumes position and cashflow data to generate daily time series records for performance and attribution analysis.

-----

## 3\. Data Flow & Kafka Topics

The system relies on a well-defined sequence of events published to Kafka topics.

  - **Raw Data Topics**: `raw_portfolios`, `raw_transactions`, `raw_instruments`, `raw_market_prices`, `raw_fx_rates`
      - **Published by**: `ingestion-service`
      - **Consumed by**: `persistence-service`
  - **Persistence Completion Topics**: `raw_transactions_completed`, `market_price_persisted`
      - **Published by**: `persistence-service`
      - **Consumed by**: Calculator services (`cost-calculator`, `cashflow-calculator`, `position-valuation-calculator`)
  - **Calculation Completion Topics**: `processed_transactions_completed`, `position_history_persisted`
      - **Published by**: Calculator services (`cost-calculator`, `position-calculator`)
      - **Consumed by**: Downstream calculator services (`position-calculator`, `position-valuation-calculator`)

-----

## 4\. API Endpoints

### Write API (`ingestion-service` @ `http://localhost:8000`)

  - `POST /ingest/portfolios`: Ingests a list of portfolios.
  - `POST /ingest/instruments`: Ingests a list of financial instruments.
  - `POST /ingest/transactions`: Ingests a list of financial transactions.
  - `POST /ingest/market-prices`: Ingests a list of market prices.
  - `POST /ingest/fx-rates`: Ingests a list of foreign exchange rates.
  - `GET /health`: Health check for the service.

### Read API (`query-service` @ `http://localhost:8001`)

  - `GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio.
  - `GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio.
  - `GET /health`: Health check for the service.

-----

## 5\. Observability

The system is designed with observability in mind, exposing metrics, health checks, and structured logs to allow for effective monitoring in a production environment.

### 5.1 Structured Logging

All services output structured JSON logs. Every log entry is enriched with a `correlation_id` that is propagated through HTTP headers and Kafka messages, allowing for easy tracing of a single request or event flow across multiple services.

### 5.2 Health Probes

Services that run background consumers (like the `persistence-service`) expose a web server with health check endpoints, making them compatible with orchestrators like Kubernetes.

  - **`persistence-service` @ `http://localhost:8080`**:
      - `GET /health/live`: Liveness probe. Returns `200 OK` if the service's process is running and responsive.
      - `GET /health/ready`: Readiness probe. Returns `200 OK` only if the service can successfully connect to its dependencies (PostgreSQL and Kafka).

### 5.3 Prometheus Metrics

Services with a web server also expose an endpoint for metrics in the Prometheus format.

  - **`persistence-service` @ `http://localhost:8080/metrics`**:
      - Provides default metrics for the health-probe API (e.g., `http_requests_total`).
      - Provides custom metrics for Kafka consumer performance:
          - `events_processed_total`: A counter for successfully processed messages, labeled by topic and consumer group.
          - `events_dlqd_total`: A counter for messages that failed all retries and were sent to the Dead-Letter Queue.
          - `event_processing_latency_seconds`: A histogram measuring the time taken to process each message.

-----

## 6\. Local Development

### Prerequisites

  - **Docker Desktop**: Must be installed and running.
  - **Python 3.11**: Must be installed and available in your system's PATH. You can download it from the [official Python website](https://www.python.org/downloads/release/python-3110/). Newer versions may not be compatible with all project dependencies.

### Initial Setup

1.  **Clone & Navigate**:
    ```bash
    git clone <repo-url> && cd portfolio-analytics-system
    ```
2.  **Create `.env` file**:
    ```bash
    cp .env.example .env
    ```
3.  **Create & Activate Virtual Environment**:
    This command explicitly creates the virtual environment using Python 3.11. On Windows with Git Bash, the `py` launcher is the most reliable way to select a specific version.
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
4.  **Install All Dependencies**: This single command will install all core tools and then install all local libraries and services in "editable" mode.
    ```bash
    pip install -r tests/requirements.txt && pip install -e libs/financial-calculator-engine \
            -e libs/portfolio-common \
            -e services/ingestion-service \
            -e services/persistence_service \
            -e services/calculators/cost_calculator_service \
            -e services/calculators/cashflow_calculator_service \
            -e services/calculators/position_calculator \
            -e services/calculators/position-valuation-calculator \
            -e services/query-service \
            -e services/timeseries-generator-service
    ```

### Running the System

  - **Start all services**:
    ```bash
    docker compose up --build -d
    ```
  - **Check service status**:
    ```bash
    docker compose ps
    ```
  - **Stop all services**:
    ```bash
    docker compose down -v
    ```

-----

## 7\. Testing

The project includes a suite of end-to-end tests that validate the full data pipeline.

1.  **Install Test Dependencies**:
    ```bash
    pip install -r tests/requirements.txt
    ```
2.  **Run Tests**:
    ```bash
    pytest tests/e2e/
    ```

-----

## 8\. Database Migrations

Database schema changes are managed by Alembic.

1.  **Ensure Postgres is Running**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration**: After changing a model in `libs/portfolio-common/portfolio_common/database_models.py`, run:
    ```bash
    alembic revision --autogenerate -m "feat: Describe your schema change"
    ```
3.  **Apply the Migration**:
    ```bash
    alembic upgrade head
    ```

-----

## 9\. Directory Structure

```
sgajbi-portfolio-analytics-system/
├── alembic/                  # Database migration scripts
├── docker/
│   └── base/                 # Base Docker image for Python services
├── libs/                     # Shared Python libraries
│   ├── portfolio-common/     # Common DB models, events, and utilities
│   └── financial-calculator-engine/ # Core financial calculation logic
├── services/                 # Individual microservices
│   ├── ingestion-service/    # The Write API
│   ├── persistence-service/  # Generic data persistence consumer
│   ├── query-service/        # The Read API
│   └── calculators/          # Business logic consumers
│       ├── cost\_calculator\_service/
│       ├── cashflow\_calculator\_service/
│       ├── position\_calculator/
│       └── position-valuation-calculator/
├── tests/
│   ├── e2e/                  # End-to-end tests for the whole system
│   ├── integration/
│   └── unit/
├── docker-compose.yml        # Orchestrates all services for local development
└── README.md                 # This file
```

-----

## 10\. Full Usage Example

This example demonstrates the full flow from ingestion to querying the final calculated position.

1.  **Start the entire system**:

    ```bash
    docker compose up --build -d
    ```

    Wait about a minute for all services to become healthy.

2.  **Ingest an Instrument (e.g., Apple Inc.)**:

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

6.  **Wait a few seconds** for all services to process these events.

7.  **Query the Final Position**:
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

8.  **Query Transactions with Cashflows**:
    Call the `query-service` to see the transaction details, including the calculated cashflow.

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/transactions
    ```

    **Expected Response**: You will see the transactions, with the BUY showing a negative (outgoing) cashflow and the SELL showing a positive (incoming) cashflow.

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

 