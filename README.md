
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sgajbi/portfolio-analytics-system)
 
# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

[cite_start]An event-driven, microservices-based platform for comprehensive portfolio analytics. [cite: 58] [cite_start]Designed for wealth management, this system ingests financial data, performs complex calculations (cost basis, positions, valuation), and exposes the results through a clean, scalable API. [cite: 58]
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

[cite_start]The system is architected around a central **Apache Kafka** message bus, promoting a highly decoupled and scalable environment. [cite: 60] [cite_start]Data flows through a choreographed pipeline of specialized microservices, each responsible for a distinct business capability. [cite: 60] [cite_start]Raw data is ingested, persisted, enriched through a series of calculations, and finally made available for query. [cite: 61]
### 1.1 Startup Sequence & Reliability

[cite_start]To guarantee data integrity and prevent errors during startup, the system employs a strict, automated startup sequence. [cite: 62]
#### Topic Creation
[cite_start]On startup, a dedicated `kafka-topic-creator` service runs first. [cite: 63] [cite_start]It connects to Kafka and idempotently creates every topic required by the entire platform, ensuring they are configured with production-ready settings (e.g., replication factor, retention). [cite: 64] [cite_start]All other services explicitly depend on the successful completion of this service. [cite: 65]
#### Service Health Checks
[cite_start]Before any consumer service begins polling for messages, it performs a startup health check. [cite: 66] [cite_start]It connects to the Kafka AdminClient and verifies that all of the topics it needs to subscribe to already exist. [cite: 67] [cite_start]The service will retry this check for up to 60 seconds. [cite: 68] [cite_start]If the topics do not appear, the service will exit with a critical error, preventing it from running in an invalid state. [cite: 69]
#### Idempotent Processing
[cite_start]To ensure data consistency and prevent duplicate calculations from event replays, all calculator services are **idempotent**. [cite: 70] This is achieved by:
1.  [cite_start]Generating a unique ID for each incoming Kafka message (from its topic, partition, and offset). [cite: 71]
2.  [cite_start]Using a shared `processed_events` table in the database. [cite: 72]
3.  [cite_start]Wrapping the business logic in an atomic transaction: the service first checks if the event ID exists in the table. [cite: 73] [cite_start]If not, it processes the data, saves the results, and inserts the event ID into the table as a single, atomic operation. [cite: 74]
4.  [cite_start]If the event ID already exists, the entire operation is skipped. [cite: 75]
```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        Client[User/Client] -- POST Data --> IngestionService[ingestion-service:8000];
        [cite_start]Client -- GET Data --> QueryService[query-service:8001]; [cite: 77]
    end

    subgraph "Kafka Message Bus"
        RawData((raw_events));
        [cite_start]PersistenceCompleted((persistence_completed)); [cite: 78]
        [cite_start]CalculationsCompleted((calculations_completed)); [cite: 78]
    end

    subgraph "Data Processing Pipeline"
        IngestionService -- Publishes --> RawData;
        [cite_start]RawData --> PersistenceService[persistence-service]; [cite: 79]
        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes --> PersistenceCompleted;

        PersistenceCompleted -- "raw_transactions_completed" --> CostCalculator[cost-calculator-service];
        [cite_start]CostCalculator -- Updates --> DB; [cite: 80]
        [cite_start]CostCalculator -- Publishes --> CalculationsCompleted; [cite: 80]
        
        PersistenceCompleted -- "raw_transactions_completed" --> CashflowCalculator[cashflow-calculator-service];
        CashflowCalculator -- Writes --> DB;
        [cite_start]CalculationsCompleted -- "processed_transactions_completed" --> PositionCalculator[position-calculator-service]; [cite: 81]
        PositionCalculator -- Writes --> DB;
        PositionCalculator -- Publishes --> CalculationsCompleted;

        CalculationsCompleted -- "position_history_persisted" --> ValuationCalculator[position-valuation-calculator];
        [cite_start]PersistenceCompleted -- "market_price_persisted" --> ValuationCalculator; [cite: 82]
        [cite_start]ValuationCalculator -- Updates --> DB; [cite: 82]
    end

    subgraph "Data Query Layer"
        [cite_start]QueryService -- Reads --> DB; [cite: 83]
    end
````

## 2\. Core Services

  - [cite\_start]**`ingestion-service`**: A write-only FastAPI application serving as the single entry point for all incoming data (portfolios, instruments, transactions, etc.). [cite: 84] [cite\_start]It validates and publishes raw events to Kafka. [cite: 85]
  - [cite\_start]**`persistence-service`**: A generic consumer responsible for persisting raw data from Kafka to the PostgreSQL database. [cite: 85] [cite\_start]On successful persistence, it publishes a `_completed` event. [cite: 86]
  - [cite\_start]**`query-service`**: A read-only FastAPI application providing access to all processed and calculated data for reporting and analytics. [cite: 86]
  - **Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic:
      - [cite\_start]**`cost-calculator-service`**: Calculates cost basis, realized gains/losses for transactions. [cite: 87]
      - [cite\_start]**`cashflow-calculator-service`**: Generates cashflow records from transactions. [cite: 88]
      - [cite\_start]**`position-calculator-service`**: Computes and maintains a historical time series of portfolio positions. [cite: 88]
      - [cite\_start]**`position-valuation-calculator`**: Calculates the market value and unrealized gain/loss of positions using the latest market prices. [cite: 89]
      - [cite\_start]**`timeseries-generator-service`**: Consumes position and cashflow data to generate daily time series records for performance and attribution analysis. [cite: 90]

-----

## 3\. Data Flow & Kafka Topics

[cite\_start]The system relies on a well-defined sequence of events published to Kafka topics. [cite: 91]

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

  - [cite\_start]`POST /ingest/portfolios`: Ingests a list of portfolios. [cite: 93]
  - [cite\_start]`POST /ingest/instruments`: Ingests a list of financial instruments. [cite: 94]
  - [cite\_start]`POST /ingest/transactions`: Ingests a list of financial transactions. [cite: 94]
  - [cite\_start]`POST /ingest/market-prices`: Ingests a list of market prices. [cite: 95]
  - [cite\_start]`POST /ingest/fx-rates`: Ingests a list of foreign exchange rates. [cite: 95]
  - [cite\_start]`GET /health`: Health check for the service. [cite: 96]

### Read API (`query-service` @ `http://localhost:8001`)

  - [cite\_start]`GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio. [cite: 96]
  - [cite\_start]`GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio. [cite: 97]
  - [cite\_start]`GET /health`: Health check for the service. [cite: 97]

-----

### **New: Sorting and Filtering**

List endpoints on the `query-service` support advanced sorting and filtering. For example, to get transactions sorted by quantity in ascending order:

```bash
curl "http://localhost:8001/portfolios/EXAMPLE_PORT_01/transactions?sort_by=quantity&sort_order=asc"
```

  - **`sort_by`**: Field to sort on. Allowed values for transactions are `transaction_date`, `quantity`, `price`, `gross_transaction_amount`.
  - **`sort_order`**: Direction of sort. Can be `asc` (ascending) or `desc` (descending).

-----

## 5\. Observability

[cite\_start]The system is designed with observability in mind, exposing metrics, health checks, and structured logs to allow for effective monitoring in a production environment. [cite: 98]

### 5.1 Structured Logging

[cite\_start]All services output structured JSON logs. [cite: 99] [cite\_start]Every log entry is enriched with a `correlation_id` that is propagated through HTTP headers and Kafka messages, allowing for easy tracing of a single request or event flow across multiple services. [cite: 99]

### 5.2 Health Probes

[cite\_start]Services that run background consumers (like the `persistence-service`) expose a web server with health check endpoints, making them compatible with orchestrators like Kubernetes. [cite: 100]

  - **`persistence-service` @ `http://localhost:8080`**:
      - [cite\_start]`GET /health/live`: Liveness probe. [cite: 101] [cite\_start]Returns `200 OK` if the service's process is running and responsive. [cite: 102]
      - [cite\_start]`GET /health/ready`: Readiness probe. [cite: 102] [cite\_start]Returns `200 OK` only if the service can successfully connect to its dependencies (PostgreSQL and Kafka). [cite: 103]

### 5.3 Prometheus Metrics

[cite\_start]Services with a web server also expose an endpoint for metrics in the Prometheus format. [cite: 104]

  - **`persistence-service` @ `http://localhost:8080/metrics`**:
      - [cite\_start]Provides default metrics for the health-probe API (e.g., `http_requests_total`). [cite: 105]
      - Provides custom metrics for Kafka consumer performance:
          - [cite\_start]`events_processed_total`: A counter for successfully processed messages, labeled by topic and consumer group. [cite: 106]
          - [cite\_start]`events_dlqd_total`: A counter for messages that failed all retries and were sent to the Dead-Letter Queue. [cite: 107]
          - [cite\_start]`event_processing_latency_seconds`: A histogram measuring the time taken to process each message. [cite: 108]
  - **`query-service` @ `http://localhost:8001/metrics`**:
      - Provides default metrics for the query API (e.g., `http_requests_total`).
      - Provides custom metrics for database performance:
          - `db_operation_latency_seconds`: A histogram measuring the time taken to execute repository methods, labeled by repository and method name.

-----

## 6\. Local Development

### Prerequisites

  - [cite\_start]**Docker Desktop**: Must be installed and running. [cite: 109]
  - [cite\_start]**Python 3.11**: Must be installed and available in your system's PATH. [cite: 110] [cite\_start]You can download it from the [official Python website](https://www.python.org/downloads/release/python-3110/). [cite: 111] [cite\_start]Newer versions may not be compatible with all project dependencies. [cite: 111]

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
    [cite\_start]This command explicitly creates the virtual environment using Python 3.11. [cite: 112] [cite\_start]On Windows with Git Bash, the `py` launcher is the most reliable way to select a specific version. [cite: 113]
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
4.  [cite\_start]**Install All Dependencies**: This single command will install all core tools and then install all local libraries and services in "editable" mode. [cite: 114]
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

[cite\_start]The project includes a suite of end-to-end tests that validate the full data pipeline. [cite: 117]

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

[cite\_start]Database schema changes are managed by Alembic. [cite: 119]

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
[cite_start]│   └── financial-calculator-engine/ # Core financial calculation logic [cite: 120]
├── services/                 # Individual microservices
[cite_start]│   ├── ingestion-service/    # The Write API [cite: 121]
[cite_start]│   ├── persistence-service/  # Generic data persistence consumer [cite: 121]
[cite_start]│   ├── query-service/        # The Read API [cite: 121]
│   └── calculators/          # Business logic consumers
│       ├── cost\_calculator\_service/
│       ├── cashflow\_calculator\_service/
│       ├── position\_calculator/
[cite_start]│       └── position-valuation-calculator/ [cite: 122]
├── tests/
[cite_start]│   ├── e2e/                  # End-to-end tests for the whole system [cite: 122]
│   ├── integration/
│   └── unit/
├── docker-compose.yml        # Orchestrates all services for local development
└── README.md                 # This file
```

-----

## 10\. Full Usage Example

[cite\_start]This example demonstrates the full flow from ingestion to querying the final calculated position. [cite: 123]

1.  **Start the entire system**:

    ```bash
    docker compose up --build -d
    ```

    [cite\_start]Wait about a minute for all services to become healthy. [cite: 124]

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

6.  [cite\_start]**Wait a few seconds** for all services to process these events. [cite: 127]

7.  **Query the Final Position**:
    [cite\_start]Call the `query-service` to see the final state of your holding. [cite: 128]

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/positions
    ```

    [cite\_start]**Expected Response**: You will get a JSON response showing the final position of 60 shares, now including valuation details. [cite: 129]

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
    [cite\_start]Call the `query-service` to see the transaction details, including the calculated cashflow. [cite: 131]

    ```bash
    curl http://localhost:8001/portfolios/EXAMPLE_PORT_01/transactions
    ```

    [cite\_start]**Expected Response**: You will see the transactions, with the BUY showing a negative (outgoing) cashflow and the SELL showing a positive (incoming) cashflow. [cite: 132]

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

 