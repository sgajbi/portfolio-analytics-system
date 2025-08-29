# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

An event-driven, microservices-based platform for comprehensive portfolio analytics. Designed for scalability and reliability, this system ingests financial data, performs complex calculations, and exposes the results through a clean, scalable API. [cite_start]It features a deterministic reprocessing engine, idempotent consumers, and a reliable outbox pattern. [cite: 115]

---
## Table of Contents

1.  [System Architecture](#1-system-architecture)
2.  [Core Services](#2-core-services)
3.  [Core Analytics Capabilities](#3-core-analytics-capabilities)
4.  [Data Flow & Kafka Topics](#4-data-flow--kafka-topics)
5.  [API Endpoints](#5-api-endpoints)
6.  [Observability](#6-observability)
7.  [Local Development](#7-local-development)
8.  [Testing](#8-testing)
9.  [Database Migrations](#9-database-migrations)
10. [Directory Structure](#10-directory-structure)
11. [Full Usage Example](#11-full-usage-example)

---
## 1. System Architecture

[cite_start]The system is architected around **Apache Kafka**, promoting a highly decoupled and scalable environment. [cite: 116] Data flows through a choreographed pipeline of specialized microservices, each responsible for a distinct business capability.

### 1.1. Deterministic Reprocessing (Epoch/Watermark Model)

[cite_start]To handle back-dated events reliably, the system uses an **epoch and watermark** model. [cite: 117]

-   [cite_start]A **key** is the combination of `(portfolio_id, security_id)`. [cite: 117]
-   [cite_start]The **epoch** is an integer version number for the history of a key. [cite: 117] [cite_start]All current data for a key shares the same epoch. [cite: 117]
-   [cite_start]The **watermark** is a date indicating how far the system has successfully calculated for a key's current epoch. [cite: 117]

[cite_start]When a back-dated event (e.g., a transaction or price) arrives, the system increments the epoch for that key, resets its watermark to a point before the event, and deterministically rebuilds its history under the new epoch. [cite: 117-118] [cite_start]**Epoch fencing** ensures that stray messages from an old epoch are safely discarded, preventing data corruption. [cite: 118]

### 1.2. Idempotent Processing & Reliability

-   [cite_start]**Idempotent Consumers**: All calculator services are idempotent. [cite: 118] [cite_start]They track processed Kafka messages in a `processed_events` table, preventing duplicate calculations from event replays. [cite: 118]
-   [cite_start]**Outbox Pattern**: Services publish events to an `outbox_events` table within the same transaction as their business logic. [cite: 118] [cite_start]A separate `OutboxDispatcher` process reliably publishes these events to Kafka, guaranteeing at-least-once delivery. [cite: 118-119]
-   [cite_start]**Partition Affinity**: Events are keyed by `portfolio_id`, ensuring all messages for a given portfolio land on the same Kafka partition and are processed sequentially. [cite: 119]

```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        Client[User/Client] -- POST Data --> IngestionService[ingestion_service:8000];
        Client -- GET Data --> QueryService[query_service:8001];
    end

    subgraph "Kafka Message Bus"
        RawData((raw_events));
        PersistenceCompleted((persistence_completed));
        CalculationsCompleted((calculations_completed));
    end

    subgraph "Data Processing Pipeline"
        [cite_start]IngestionService -- Publishes --> RawData; [cite: 120]
        [cite_start]RawData --> PersistenceService[persistence-service]; [cite: 120]
        [cite_start]PersistenceService -- Writes --> DB[(PostgreSQL)]; [cite: 120]
        [cite_start]PersistenceService -- Publishes via Outbox --> PersistenceCompleted; [cite: 120]

        [cite_start]PersistenceCompleted -- "raw_transactions_completed" --> CostCalculator[cost-calculator-service]; [cite: 120]
        [cite_start]CostCalculator -- Updates --> DB; [cite: 120]
        [cite_start]CostCalculator -- Publishes via Outbox --> CalculationsCompleted; [cite: 120]
        
        [cite_start]PersistenceCompleted -- "raw_transactions_completed" --> CashflowCalculator[cashflow-calculator-service]; [cite: 120]
        [cite_start]CashflowCalculator -- Writes --> DB; [cite: 120]

        [cite_start]CalculationsCompleted -- "processed_transactions_completed" --> PositionCalculator[position-calculator-service]; [cite: 120]
        [cite_start]PositionCalculator -- Writes --> DB; [cite: 120]
        [cite_start]PositionCalculator -- Publishes via Outbox --> CalculationsCompleted; [cite: 120]

        [cite_start]CalculationsCompleted -- "position_history_persisted" --> ValuationCalculator[position-valuation-calculator]; [cite: 120]
        [cite_start]PersistenceCompleted -- "market_price_persisted" --> ValuationCalculator; [cite: 120]
        [cite_start]ValuationCalculator -- Updates --> DB; [cite: 120]
    end

    [cite_start]subgraph "Data Query Layer" [cite: 120]
        [cite_start]QueryService -- Reads --> DB; [cite: 121]
    end
````

## 2\. Core Services

  - [cite\_start]**`ingestion_service`**: A write-only FastAPI application serving as the single entry point for all incoming data. [cite: 121]
  - [cite\_start]**`persistence-service`**: Consumes raw data events and persists them to the PostgreSQL database. [cite: 121]
  - [cite\_start]**`query-service`**: A read-only FastAPI application providing a comprehensive set of endpoints to access all processed data. [cite: 121]
  - [cite\_start]**Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic: [cite: 121]
      - [cite\_start]**`cost-calculator-service`**: Calculates cost basis and realized gains/losses for transactions. [cite: 121-122]
      - [cite\_start]**`cashflow-calculator-service`**: Generates cashflow records from transactions. [cite: 122]
      - [cite\_start]**`position-calculator-service`**: Computes a historical time series of portfolio positions and triggers reprocessing for back-dated events. [cite: 122]
      - [cite\_start]**`position-valuation-calculator`**: Calculates the market value of positions and schedules valuation jobs. [cite: 122]
      - [cite\_start]**`timeseries-generator-service`**: Aggregates daily data for performance analysis. [cite: 122]

-----

## 3\. Core Analytics Capabilities

The `query-service` exposes powerful, on-the-fly analytical capabilities.

### 3.1. Performance Analytics

The system can calculate **Time-Weighted Return (TWR)** and **Money-Weighted Return (MWR)** for any portfolio over configurable time periods. These calculations are performed dynamically using the underlying daily time-series data.

  - `POST /portfolios/{portfolio_id}/performance` (TWR)
  - `POST /portfolios/{portfolio_id}/performance/mwr` (MWR)

### 3.2. Risk Analytics

A suite of industry-standard risk metrics can be calculated on-demand, ensuring consistency with performance figures by using the same daily return data.

  - **Metrics Available**: Volatility, Sharpe Ratio, Sortino Ratio, Drawdown, Beta, Tracking Error, Information Ratio, and Value at Risk (VaR).
  - **Endpoint**: `POST /portfolios/{portfolio_id}/risk`

For a complete guide on the API, calculation methodologies, and operational details, see the **[Risk Analytics Feature Documentation](https://www.google.com/search?q=./docs/features/risk_analytics/01_Feature_Risk_Analytics_Overview.md)**.

-----

## 4\. Data Flow & Kafka Topics

[cite\_start]The system relies on a well-defined sequence of events published to Kafka topics. [cite: 122]

  - [cite\_start]**Raw Data Topics**: `raw_portfolios`, `raw_transactions`, `raw_instruments`, `raw_market_prices`, `raw_fx_rates`, `raw_business_dates` [cite: 122]
  - [cite\_start]**Persistence Completion Topics**: `raw_transactions_completed`, `market_price_persisted` [cite: 122]
  - [cite\_start]**Calculation Completion Topics**: `processed_transactions_completed`, `daily_position_snapshot_persisted` [cite: 122]
  - [cite\_start]**Job & Scheduling Topics**: `valuation_required`, `portfolio_aggregation_required` [cite: 122-123]
  - [cite\_start]**Reprocessing Topics**: `transactions_reprocessing_requested` [cite: 123]

-----

## 5\. API Endpoints

### Write API (`ingestion_service` @ `http://localhost:8000`)

  - [cite\_start]`POST /ingest/portfolios`: Ingests a list of portfolios. [cite: 123]
  - [cite\_start]`POST /ingest/instruments`: Ingests a list of financial instruments. [cite: 123]
  - [cite\_start]`POST /ingest/transactions`: Ingests a list of financial transactions. [cite: 123]
  - [cite\_start]`POST /ingest/market-prices`: Ingests a list of market prices. [cite: 123]
  - [cite\_start]`POST /ingest/fx-rates`: Ingests a list of foreign exchange rates. [cite: 123]
  - [cite\_start]`POST /reprocess/transactions`: Triggers a reprocessing flow for a list of transaction IDs. [cite: 123]
  - [cite\_start]`GET /health/ready`: Readiness probe (checks Kafka connection). [cite: 123]

### Read API (`query-service` @ `http://localhost:8001`)

  - [cite\_start]`GET /portfolios/{portfolio_id}`: Retrieves details for a single portfolio. [cite: 123-124]
  - [cite\_start]`GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio. [cite: 124]
  - [cite\_start]`GET /portfolios/{portfolio_id}/position-history`: Retrieves the historical time series of positions for a security. [cite: 124]
  - [cite\_start]`GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio. [cite: 124]
  - [cite\_start]`POST /portfolios/{portfolio_id}/performance`: Calculates Time-Weighted Return (TWR) for a portfolio. [cite: 124]
  - [cite\_start]`POST /portfolios/{portfolio_id}/performance/mwr`: Calculates Money-Weighted Return (MWR) for a portfolio. [cite: 124]
  - `POST /portfolios/{portfolio_id}/risk`: Calculates a suite of on-demand risk analytics.
  - [cite\_start]`GET /health/ready`: Readiness probe (checks database connection). [cite: 124]

-----

## 6\. Observability

  - [cite\_start]**Structured Logging**: All services output structured JSON logs enriched with a `correlation_id` for easy tracing. [cite: 124]
  - [cite\_start]**Health Probes**: All services expose `GET /health/live` and `GET /health/ready` endpoints, compatible with orchestrators like Kubernetes. [cite: 124-125]
  - [cite\_start]**Prometheus Metrics**: All services expose a `/metrics` endpoint for scraping key performance indicators, including Kafka consumer lag, database latency, and outbox queue size. [cite: 125]

-----

## 7\. Local Development

### Prerequisites

  - [cite\_start]**Docker Desktop**: Must be installed and running. [cite: 125]
  - [cite\_start]**Python 3.11**: Must be installed. [cite: 125] [cite\_start]Using the `py` launcher on Windows is recommended. [cite: 125]

### Initial Setup

1.  **Clone & Navigate**:
    ```bash
    git clone <repo-url> && cd portfolio-analytics-system
    ```
2.  [cite\_start]**Open in VSCode**: [cite: 125]
    ```bash
    code .
    ```
3.  [cite\_start]**Create `.env` file**: [cite: 126]
    ```bash
    cp .env.example .env
    ```
4.  [cite\_start]**Create & Activate Virtual Environment**: [cite: 126]
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
5.  [cite\_start]**Install All Dependencies**: [cite: 126]
    ```bash
    pip install -r tests/requirements.txt
    pip install -e src/libs/portfolio-common
    pip install -e src/libs/financial-calculator-engine
    pip install -e src/libs/performance-calculator-engine
    pip install -e src/services/ingestion_service
    pip install -e src/services/persistence_service
    pip install -e src/services/query_service
    pip install -e src/services/calculators/cashflow_calculator_service
    pip install -e src/services/calculators/cost_calculator_service
    pip install -e src/services/calculators/position_calculator
    pip install -e src/services/calculators/position_valuation_calculator
    pip install -e src/services/timeseries_generator_service
    ```

### Running the System

  - [cite\_start]**Start all services**: [cite: 127]
    ```bash
    docker compose up --build -d
    ```
  - [cite\_start]**Stop all services and remove volumes**: [cite: 127]
    ```bash
    docker compose down -v
    ```
  - [cite\_start]**View logs for a specific service**: [cite: 128]
    ```bash
    docker compose logs -f persistence-service
    ```

-----

## 8\. Testing

[cite\_start]The project contains a comprehensive suite of unit, integration, and end-to-end tests. [cite: 128]

1.  [cite\_start]**Run All Unit Tests**: These are fast and do not require Docker. [cite: 128]
    ```bash
    pytest tests/unit/
    ```
2.  [cite\_start]**Run All Integration & E2E Tests**: These require the full Docker environment to be running. [cite: 128]
    ```bash
    # Ensure all services are running
    [cite_start]docker compose up --build -d [cite: 129]

    # Run all tests
    [cite_start]pytest [cite: 129]
    ```
3.  [cite\_start]**Clean Docker Build Cache**: If you encounter strange build errors related to "parent snapshots", run this command to clean the Docker cache. [cite: 129]
    ```bash
    docker builder prune -a
    ```
4.  [cite\_start]**Generate Coverage Reports**: [cite: 129]
    ```bash
    # Generate an interactive HTML report for the full suite
    [cite_start]pytest --cov=src --cov-report=html [cite: 129]
    ```
    [cite\_start]After running, open `htmlcov/index.html` in your browser. [cite: 130]

-----

## 9\. Database Migrations

[cite\_start]Database schema changes are managed by Alembic. [cite: 130]

1.  [cite\_start]**Ensure Postgres is Running**: [cite: 130]
    ```bash
    docker compose up -d postgres
    ```
2.  [cite\_start]**Generate a New Migration**: After changing a model in `portfolio_common/database_models.py`, run: [cite: 130]
    ```bash
    alembic revision --autogenerate -m "feat: Describe your schema change"
    ```
3.  [cite\_start]**Apply the Migration**: [cite: 130]
    ```bash
    alembic upgrade head
    ```

-----

## 10\. Directory Structure

```
sgajbi-portfolio-analytics-system/
[cite_start]├── alembic/                      # Database migration scripts. [cite: 131]
[cite_start]├── docker-compose.yml            # Orchestrates all services for local development. [cite: 131]
├── src/
[cite_start]│   ├── libs/                     # Shared Python libraries. [cite: 131]
[cite_start]│   │   ├── financial-calculator-engine/ [cite: 131]
[cite_start]│   │   ├── performance-calculator-engine/ [cite: 132]
[cite_start]│   │   └── portfolio-common/     # Common code: DB models, Kafka utils, etc. [cite: 132]
[cite_start]│   └── services/                 # All individual microservices. [cite: 132]
│       ├── calculators/
[cite_start]│       ├── ingestion_service/    # Write API [cite: 132]
│       ├── persistence_service/
[cite_start]│       ├── query_service/        # Read API [cite: 132-133]
│       └── timeseries_generator_service/
├── tests/
[cite_start]│   ├── e2e/                      # End-to-end tests for full data pipelines. [cite: 133]
[cite_start]│   ├── integration/              # Tests for component interaction (e.g., service -> DB). [cite: 133]
[cite_start]│   └── unit/                     # Tests for isolated business logic. [cite: 133-134]
[cite_start]└── tools/                        # Standalone scripts for development/ops tasks. [cite: 134]
```

-----

## 11\. Full Usage Example

[cite\_start]This example demonstrates the full flow from ingesting data to querying the final calculated position. [cite: 134]

1.  [cite\_start]**Start the entire system**: [cite: 134]

    ```bash
    docker compose up --build -d
    ```

    [cite\_start]Wait about a minute for all services to become healthy. [cite: 134-135] [cite\_start]You can check the status with `docker compose ps`. [cite: 135]

2.  [cite\_start]**Run the Example Script**: [cite: 135]
    [cite\_start]This script will ingest all the necessary data and then query the final results. [cite: 135]

    ```bash
    ./scripts/run_e2e_example.sh
    ```

    [cite\_start]The script will print the final `positions` and `transactions` JSON responses to the console. [cite: 135]

<!-- end list -->
