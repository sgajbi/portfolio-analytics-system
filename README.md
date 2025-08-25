
# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

An event-driven, microservices-based platform for comprehensive portfolio analytics. Designed for scalability and reliability, this system ingests financial data, performs complex calculations (cost basis, positions, valuation, and time series), and exposes the results through a clean, scalable API. It leverages an outbox pattern for guaranteed event delivery and idempotent consumers to ensure data consistency.

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
10. [Full Usage Example](#10-full-usage-example)

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
3.  Wrapping the business logic in an atomic transaction: the service first checks if the event ID exists in the table.
4.  If not, it processes the data, saves the results, and inserts the event ID into the table as a single, atomic operation.
5.  If the event ID already exists, the entire operation is skipped.

### 1.2 Partition Affinity & Ordering

To guarantee that all events related to a single portfolio are processed in the correct order, events are keyed by **`portfolio_id`**. This ensures that all messages for a given portfolio land on the same Kafka partition, preventing race conditions and ensuring that downstream consumers receive updates for a specific portfolio sequentially.

```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        Client[User/Client] -- POST Data --> IngestionService[ingestion_service:8000];
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

  - **`ingestion_service`**: A write-only FastAPI application serving as the single entry point for all incoming data (portfolios, instruments, transactions, etc.). It validates data and publishes raw events to Kafka.
  - **`persistence-service`**: A generic consumer responsible for persisting raw data from Kafka to the PostgreSQL database. On successful persistence, it publishes a `_completed` event to an outbox for reliable downstream processing.
  - **`query-service`**: A read-only FastAPI application providing a comprehensive set of endpoints to access all processed data. It handles on-the-fly calculations for complex queries like Time-Weighted Return (TWR) performance.
  - **Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic:
      - **`cost-calculator-service`**: Calculates cost basis and realized gains/losses for transactions, with full support for dual-currency trades.
      - **`cashflow-calculator-service`**: Generates cashflow records from transactions based on configurable business rules.
      - **`position-calculator-service`**: Computes and maintains a historical time series of portfolio positions, including dual-currency cost basis. It is designed to correctly handle back-dated transactions.
      - **`position-valuation-calculator`**: Calculates the market value and unrealized gain/loss of positions using the latest market prices and FX rates.
      - **`timeseries-generator-service`**: Consumes position and cashflow data to generate daily, aggregated time series records at both the position and portfolio level, which serve as the foundation for performance calculations.

-----

## 3\. Data Flow & Kafka Topics

The system relies on a well-defined sequence of events published to Kafka topics.

  - **Raw Data Topics**: `raw_portfolios`, `raw_transactions`, `raw_instruments`, `raw_market_prices`, `raw_fx_rates`
      - **Published by**: `ingestion_service`
      - **Consumed by**: `persistence-service`
  - **Persistence Completion Topics**: `raw_transactions_completed`, `market_price_persisted`
      - **Published by**: `persistence-service` (via outbox)
      - **Consumed by**: Calculator services (`cost-calculator`, `cashflow-calculator`, `position-valuation-calculator`)
  - **Calculation Completion Topics**: `processed_transactions_completed`, `position_history_persisted`, `daily_position_snapshot_persisted`
      - **Published by**: Calculator services (`cost-calculator`, `position-calculator`, `position-valuation-calculator`) (via outbox)
      - **Consumed by**: Downstream calculator services (`position-calculator`, `position-valuation-calculator`, `timeseries-generator-service`)

-----

## 4\. API Endpoints

### Write API (`ingestion_service` @ `http://localhost:8000`)

  - `POST /ingest/portfolios`: Ingests a list of portfolios.
  - `POST /ingest/instruments`: Ingests a list of financial instruments.
  - `POST /ingest/transactions`: Ingests a list of financial transactions.
  - `POST /ingest/market-prices`: Ingests a list of market prices.
  - `POST /ingest/fx-rates`: Ingests a list of foreign exchange rates.
  - `GET /health/live`: Liveness probe for the service.
  - `GET /health/ready`: Readiness probe (checks Kafka connection).

### Read API (`query-service` @ `http://localhost:8001`)

  - `GET /portfolios/`: Retrieves details for portfolios, filterable by `cif_id`, or `booking_center`.
  - `GET /portfolios/{portfolio_id}`: Retrieves details for a single portfolio. Returns `404` if not found.
  - `GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio, including dual-currency valuation.
  - `GET /portfolios/{portfolio_id}/position-history`: Retrieves the historical time series of positions for a specific security within a portfolio.
  - `GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio, including dual-currency costs and P\&L. Supports sorting and filtering.
  - `POST /portfolios/{portfolio_id}/performance`: Calculates Time-Weighted Return (TWR) for a portfolio over one or more specified periods. Supports multiple period types (MTD, YTD, SI, etc.), Net/Gross calculations, and currency overrides in a single request.
  - `GET /instruments/`: Retrieves a paginated list of all financial instruments.
  - `GET /prices/`: Retrieves historical market prices for a security.
  - `GET /fx-rates/`: Retrieves historical FX rates for a currency pair.
  - `GET /health/live`: Liveness probe for the service.
  - `GET /health/ready`: Readiness probe (checks database connection).

### 4.1 Performance API Example

The performance endpoint is highly flexible. You can request multiple, named periods in a single call.

**Example Request:** `POST http://localhost:8001/portfolios/E2E_ADV_PERF_01/performance`

```json
{
    "scope": {
        "as_of_date": "2025-03-11",
        "net_or_gross": "NET"
    },
    "periods": [
        { "name": "Month To Date", "type": "MTD" },
        { 
          "name": "SpecificRange",
          "type": "EXPLICIT",
          "from": "2025-03-10",
          "to": "2025-03-11"
        }
    ],
    "options": { "include_cumulative": true, "include_annualized": false, "include_attributes": true }
}
```

**Example Response:**

```json
{
    "scope": {
        "as_of_date": "2025-03-11",
        "reporting_currency": null,
        "net_or_gross": "NET"
    },
    "summary": {
        "Month To Date": {
            "start_date": "2025-03-01",
            "end_date": "2025-03-11",
            "cumulative_return": 5.000000000000004,
            "annualized_return": null,
            "attributes": {
                "begin_market_value": "0.0000000000",
                "end_market_value": "10500.0000000000",
                "total_cashflow": "10000.0000000000",
                "fees": "0.0000000000"
            }
        },
        "SpecificRange": {
            "start_date": "2025-03-10",
            "end_date": "2025-03-11",
            "cumulative_return": 5.000000000000004,
            "annualized_return": null,
            "attributes": {
                "begin_market_value": "0.0000000000",
                "end_market_value": "10500.0000000000",
                "total_cashflow": "10000.0000000000",
                "fees": "0.0000000000"
            }
        }
    },
    "breakdowns": null
}
```

-----

## 5\. Observability

The system is designed with observability in mind, exposing metrics, health checks, and structured logs to allow for effective monitoring in a production environment.

### 5.1 Structured Logging

All services output structured JSON logs. Every log entry is enriched with a `correlation_id` that is propagated through HTTP headers and Kafka messages, allowing for easy tracing of a single request or event flow across multiple services.

### 5.2 Health Probes

All services that run as background workers (all consumers and APIs) expose a web server with standardized health check endpoints, making them compatible with orchestrators like Kubernetes.

  - `GET /health/live`: Liveness probe. Returns `200 OK` if the service's process is running.
  - `GET /health/ready`: Readiness probe. Returns `200 OK` only if the service can successfully connect to its dependencies (e.g., PostgreSQL and Kafka).

### 5.3 Prometheus Metrics

All services with a web server also expose an endpoint at `/metrics` for scraping in the Prometheus format. Custom metrics are available for Kafka consumer performance and database operation latency.

-----

## 6\. Local Development

### Prerequisites

  - **Docker Desktop**: Must be installed and running.
  - **Python 3.11**: Must be installed and available in your system's PATH. You can download it from the [official Python website](https://www.python.org/downloads/release/python-3110/).

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
    This file stores local configuration and secrets, and is ignored by Git.
    ```bash
    cp .env.example .env
    ```
4.  **Create & Activate Virtual Environment**:
    This command explicitly creates the virtual environment using Python 3.11. On Windows with Git Bash, the `py` launcher is the most reliable way to select a specific version.
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
5.  **Install All Dependencies**: This command installs test requirements and then installs all local libraries and services in "editable" mode so that changes are reflected immediately.
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

  - **Start all services**:
    ```bash
    docker compose up --build -d
    ```
  - **Check service status**:
    ```bash
    docker compose ps
    ```
  - **View logs for a specific service**:
    ```bash
    docker compose logs -f persistence-service
    ```
  - **Stop all services**:
    ```bash
    docker compose down -v
    ```

-----

## 7\. Testing

The project contains a comprehensive suite of tests to ensure correctness and reliability.

1.  **Install Test Dependencies**: Ensure you have completed the "Initial Setup" steps, which includes this command.
    ```bash
    pip install -r tests/requirements.txt
    ```
2.  **Run All Tests**: To run the complete test suite (unit, integration, and end-to-end), first start the Docker environment, then run pytest.
    ```bash
    # Ensure all services are running
    docker compose up -d

    # Run all tests
    pytest
    ```
3.  **Run Specific Tests**: To run tests for a single part of the application, specify the directory or file path.
    ```bash
    # Run all unit tests for the financial calculator
    pytest tests/unit/libs/financial-calculator-engine/

    # Run the new E2E test for the performance pipeline
    pytest tests/e2e/test_performance_pipeline.py

    # Run the comprehensive 5-day workflow test
    pytest tests/e2e/test_5_day_workflow.py
    ```
4.  **Generate Coverage Reports**: To measure which lines of code are executed by the tests, run pytest with coverage flags.
    ```bash
    # Generate a quick summary in the terminal (useful for unit tests)
    pytest tests/unit/ --cov=src --cov-report term-missing

    # Generate a detailed, interactive HTML report for the full suite
    pytest --cov=src --cov-report=html
    ```
    After running, open the `htmlcov/index.html` file in your browser to explore the coverage report.

-----

## 8\. Database Migrations

Database schema changes are managed by Alembic.

1.  **Ensure Postgres is Running**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration**: After changing a model in `src/libs/portfolio-common/portfolio_common/database_models.py`, run:
    ```bash
    alembic revision --autogenerate -m "feat: Describe your schema change"
    ```
3.  **Apply the Migration**:
    ```bash
    alembic upgrade head
    ```

-----

## 9\. Directory Structure

A detailed overview of the project layout.

```
sgajbi-portfolio-analytics-system/
├── alembic/                      # Database migration scripts managed by Alembic.
├── docker-compose.yml            # Orchestrates all services for local development.
├── pyproject.toml                # Project definition and dependencies for the root installer.
├── scripts/
│   └── run_e2e_example.sh        # A script to run the full usage example.
├── src/
│   ├── libs/                     # Shared Python libraries, installable as packages.
│   │   ├── financial-calculator-engine/ # Core stateless financial calculation logic.
│   │   └── portfolio-common/     # Common code: DB models, events, Kafka utils, etc.
│   │
│   └── services/                 # All individual microservices.
│       ├── calculators/          # Services that perform business logic calculations.
│       │   ├── cashflow_calculator_service/
│       │   ├── cost_calculator_service/
│       │   ├── position_calculator/
│       │   └── position_valuation_calculator/
│       │
│       ├── ingestion_service/    # The public-facing Write API (FastAPI).
│       ├── persistence_service/  # Consumes from raw topics and saves to the database.
│       ├── query_service/        # The public-facing Read API (FastAPI).
│       └── timeseries_generator_service/ # Aggregates daily data for performance analysis.
│
├── tests/
│   ├── e2e/                      # End-to-end tests that validate full data pipelines.
│   ├── integration/              # Tests for component interaction (e.g., service -> DB).
│   └── unit/                     # Tests for isolated business logic and components.
│
├── tools/                        # Standalone scripts for development/ops tasks.
│   ├── db_reset_head.py          # Utility to fix a broken Alembic migration head.
│   ├── dlq_replayer.py           # Script to consume and republish messages from a DLQ.
│   └── kafka_setup.py            # Idempotently creates all required Kafka topics.
│
└── README.md                     # This file.
```

-----

## 10\. Full Usage Example

This example demonstrates the full flow from ingesting a cross-currency trade to querying the final calculated position with dual-currency P\&L.

1.  **Start the entire system**:

    ```bash
    docker compose up --build -d
    ```

    Wait about a minute for all services to become healthy.

2.  **Run the Example Script**:
    This script will ingest all the necessary data and then query the final results.

    ```bash
    ./scripts/run_e2e_example.sh
    ```

    The script will print the final `positions` and `transactions` JSON responses to the console, which should match the expected output shown in the previous version of this README.

<!-- end list -->
 
 