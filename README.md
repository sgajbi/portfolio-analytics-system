# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

An event-driven, microservices-based platform for comprehensive portfolio analytics. Designed for scalability and reliability, this system ingests financial data, performs complex calculations, and exposes the results through a clean, scalable API. It features a deterministic reprocessing engine, idempotent consumers, and a reliable outbox pattern.
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

The system is architected around **Apache Kafka**, promoting a highly decoupled and scalable environment. Data flows through a choreographed pipeline of specialized microservices, each responsible for a distinct business capability.

### 1.1. Deterministic Reprocessing (Epoch/Watermark Model)

To handle back-dated events reliably, the system uses an **epoch and watermark** model.

-   A **key** is the combination of `(portfolio_id, security_id)`.
-   The **epoch** is an integer version number for the history of a key.
All current data for a key shares the same epoch.
-   The **watermark** is a date indicating how far the system has successfully calculated for a key's current epoch.

When a back-dated event (e.g., a transaction or price) arrives, the system increments the epoch for that key, resets its watermark to a point before the event, and deterministically rebuilds its history under the new epoch. **Epoch fencing** ensures that stray messages from an old epoch are safely discarded, preventing data corruption.

### 1.2. Idempotent Processing & Reliability

-   **Idempotent Consumers**: All calculator services are idempotent. They track processed Kafka messages in a `processed_events` table, preventing duplicate calculations from event replays.
-   **Outbox Pattern**: Services publish events to an `outbox_events` table within the same transaction as their business logic. A separate `OutboxDispatcher` process reliably publishes these events to Kafka, guaranteeing at-least-once delivery.
-   **Partition Affinity**: Events are keyed by `portfolio_id`, ensuring all messages for a given portfolio land on the same Kafka partition and are processed sequentially.

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
        IngestionService -- Publishes --> RawData;
        RawData --> PersistenceService[persistence-service];
        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes via Outbox --> PersistenceCompleted;

        PersistenceCompleted -- "raw_transactions_completed" --> CostCalculator[cost-calculator-service];
        CostCalculator -- Updates --> DB;
        CostCalculator -- Publishes via Outbox --> CalculationsCompleted;
        
        PersistenceCompleted -- "raw_transactions_completed" --> CashflowCalculator[cashflow-calculator-service];
        CashflowCalculator -- Writes --> DB;

        CalculationsCompleted -- "processed_transactions_completed" --> PositionCalculator[position-calculator-service];
        PositionCalculator -- Writes --> DB;
        PositionCalculator -- Publishes via Outbox --> CalculationsCompleted;

        CalculationsCompleted -- "position_history_persisted" --> ValuationCalculator[position-valuation-calculator];
        PersistenceCompleted -- "market_price_persisted" --> ValuationCalculator;
        ValuationCalculator -- Updates --> DB;
    end

    subgraph "Data Query Layer"
        QueryService -- Reads --> DB;
end
````

## 2\. Core Services

  - **`ingestion_service`**: A write-only FastAPI application serving as the single entry point for all incoming data.
  - **`persistence-service`**: Consumes raw data events and persists them to the PostgreSQL database.
  - **`query-service`**: A read-only FastAPI application providing a comprehensive set of endpoints to access all processed data.
  - **Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic:
      - **`cost-calculator-service`**: Calculates cost basis and realized gains/losses for transactions.
      - **`cashflow-calculator-service`**: Generates cashflow records from transactions.
      - **`position-calculator-service`**: Computes a historical time series of portfolio positions and triggers reprocessing for back-dated events.
      - **`position-valuation-calculator`**: Calculates the market value of positions and schedules valuation jobs.
      - **`timeseries-generator-service`**: Aggregates daily data for performance analysis.

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

### 3.3. Portfolio Summary & Allocation

A consolidated, dashboard-style view of a portfolio's state can be retrieved for any date and period. This is designed to efficiently populate a UI with a single API call.

  - **Data Available**: Total Wealth, P\&L Summary, Income & Activity totals, and multi-dimensional Asset Allocation (by asset class, sector, country, etc.).
  - **Endpoint**: `POST /portfolios/{portfolio_id}/summary`

For a complete guide, see the **[Portfolio Summary Feature Documentation](https://www.google.com/search?q=./docs/features/portfolio_summary/01_Feature_Portfolio_Summary_Overview.md)**.

-----

## 4\. Data Flow & Kafka Topics

The system relies on a well-defined sequence of events published to Kafka topics.

  - **Raw Data Topics**: `raw_portfolios`, `raw_transactions`, `raw_instruments`, `raw_market_prices`, `raw_fx_rates`, `raw_business_dates`
  - **Persistence Completion Topics**: `raw_transactions_completed`, `market_price_persisted`
  - **Calculation Completion Topics**: `processed_transactions_completed`, `daily_position_snapshot_persisted`
  - **Job & Scheduling Topics**: `valuation_required`, `portfolio_aggregation_required`
  - **Reprocessing Topics**: `transactions_reprocessing_requested`

-----

## 5\. API Endpoints

### Write API (`ingestion_service` @ `http://localhost:8000`)

  - `POST /ingest/portfolios`: Ingests a list of portfolios.
  - `POST /ingest/instruments`: Ingests a list of financial instruments.
  - `POST /ingest/transactions`: Ingests a list of financial transactions.
  - `POST /ingest/market-prices`: Ingests a list of market prices.
  - `POST /ingest/fx-rates`: Ingests a list of foreign exchange rates.
  - `POST /reprocess/transactions`: Triggers a reprocessing flow for a list of transaction IDs.
  - `GET /health/ready`: Readiness probe (checks Kafka connection).

### Read API (`query-service` @ `http://localhost:8001`)

  - `GET /portfolios/{portfolio_id}`: Retrieves details for a single portfolio.
  - `GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio.
  - `GET /portfolios/{portfolio_id}/position-history`: Retrieves the historical time series of positions for a security.
  - `GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio.
  - `POST /portfolios/{portfolio_id}/performance`: Calculates Time-Weighted Return (TWR) for a portfolio.
  - `POST /portfolios/{portfolio_id}/performance/mwr`: Calculates Money-Weighted Return (MWR) for a portfolio.
  - `POST /portfolios/{portfolio_id}/risk`: Calculates a suite of on-demand risk analytics.
  - `POST /portfolios/{portfolio_id}/summary`: Calculates a consolidated, on-demand summary of portfolio wealth, P\&L, and allocation.
  - `POST /portfolios/{portfolio_id}/review`: **(NEW)** Generates a comprehensive, multi-section portfolio review report with a single API call.
  - `GET /health/ready`: Readiness probe (checks database connection).

-----

## 6\. Observability

  - **Structured Logging**: All services output structured JSON logs enriched with a `correlation_id` for easy tracing.
  - **Health Probes**: All services expose `GET /health/live` and `GET /health/ready` endpoints, compatible with orchestrators like Kubernetes.
  - **Prometheus Metrics**: All services expose a `/metrics` endpoint for scraping key performance indicators, including Kafka consumer lag, database latency, and outbox queue size.

-----

## 7\. Local Development

### Prerequisites

  - **Docker Desktop**: Must be installed and running.
  - **Python 3.11**: Must be installed. Using the `py` launcher on Windows is recommended.

### Initial Setup

1.  **Clone & Navigate**:
    ```bash
    git clone <repo-url> && cd portfolio-analytics-system
    ```
2.  **Open in VSCode**:
    ```bash
    code .
    ```
3.  **Create `.env` file**:
    ```bash
    cp .env.example .env
    ```
4.  **Create & Activate Virtual Environment**:
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
5.  **Install All Dependencies**:
    ```bash
    pip install -r tests/requirements.txt
    pip install -e src/libs/portfolio-common
    pip install -e src/libs/financial-calculator-engine
    pip install -e src/libs/performance-calculator-engine
    pip install -e src/libs/risk-analytics-engine
    pip install -e src/libs/concentration-analytics-engine
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

  - **Start all services**:
    ```bash
    docker compose up --build -d
    ```
  - **Stop all services and remove volumes**:
    ```bash
    docker compose down -v
    ```
  - **View logs for a specific service**:
    ```bash
    docker compose logs -f persistence-service
    ```

-----

## 8\. Testing

The project contains a comprehensive suite of unit, integration, and end-to-end tests.

1.  **Run All Unit Tests**: These are fast and do not require Docker.
    ```bash
    pytest tests/unit/
    ```
2.  **Run All Integration & E2E Tests**: These require the full Docker environment to be running.
    ```bash
    # Ensure all services are running
    docker compose up --build -d

    # Run all tests
    pytest
    ```
3.  **Clean Docker Build Cache**: If you encounter strange build errors related to "parent snapshots", run this command to clean the Docker cache.
    ```bash
    docker builder prune -a
    ```
4.  **Generate Coverage Reports**:
    ```bash
    # Generate an interactive HTML report for the full suite
    pytest --cov=src --cov-report=html
    ```
    After running, open `htmlcov/index.html` in your browser.

-----

## 9\. Database Migrations

Database schema changes are managed by Alembic.

1.  **Ensure Postgres is Running**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration**: After changing a model in `portfolio_common/database_models.py`, run:
    ```bash
    alembic revision --autogenerate -m "feat: Describe your schema change"
    ```
3.  **Apply the Migration**:
    ```bash
    alembic upgrade head
    ```

-----

## 10\. Directory Structure

```
sgajbi-portfolio-analytics-system/
├── alembic/                      # Database migration scripts.
├── docker-compose.yml            # Orchestrates all services for local development.
└── src/
    ├── libs/                     # Shared Python libraries.
    │   ├── financial-calculator-engine/
    │   ├── performance-calculator-engine/
    │   └── portfolio-common/     # Common code: DB models, Kafka utils, etc.
    └── services/                 # All individual microservices.
        ├── calculators/
        ├── ingestion_service/    # Write API
        ├── persistence_service/
        ├── query_service/        # Read API
        └── timeseries_generator_service/
└── tests/
    ├── e2e/                      # End-to-end tests for full data pipelines.
    ├── integration/              # Tests for component interaction (e.g., service -> DB).
    └── unit/                     # Tests for isolated business logic.
└── tools/                        # Standalone scripts for development/ops tasks.
```

-----

## 11\. Full Usage Example

This example demonstrates the full flow from ingesting data to querying the final calculated position.

1.  **Start the entire system**:

    ```bash
    docker compose up --build -d
    ```

    Wait about a minute for all services to become healthy. You can check the status with `docker compose ps`.

2.  **Run the Example Script**:
    This script will ingest all the necessary data and then query the final results.

    ```bash
    ./scripts/run_e2e_example.sh
    ```

    The script will print the final `positions` and `transactions` JSON responses to the console.

<!-- end list -->
