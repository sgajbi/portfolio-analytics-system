
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/sgajbi/portfolio-analytics-system)
 
# Portfolio Analytics System

[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Kafka](https://img.shields.io/badge/Apache%20Kafka-231F20?style=for-the-badge&logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![Postgres](https://img.shields.io/badge/postgresql-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)

[cite_start]An event-driven, microservices-based platform for comprehensive portfolio analytics. [cite: 69] [cite_start]Designed for wealth management, this system ingests financial data, performs complex calculations (cost basis, positions, valuation), and exposes the results through a clean, scalable API. [cite: 70]
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

[cite_start]The system is architected around a central **Apache Kafka** message bus, promoting a highly decoupled and scalable environment. [cite: 71] [cite_start]Data flows through a choreographed pipeline of specialized microservices, each responsible for a distinct business capability. [cite: 72] [cite_start]Raw data is ingested, persisted, enriched through a series of calculations, and finally made available for query. [cite: 73]
### 1.1 Startup Sequence & Reliability

[cite_start]To guarantee data integrity and prevent errors during startup, the system employs a strict, automated startup sequence. [cite: 74]
#### Topic Creation
[cite_start]On startup, a dedicated `kafka-topic-creator` service runs first. [cite: 75] [cite_start]It connects to Kafka and idempotently creates every topic required by the entire platform, ensuring they are configured with production-ready settings (e.g., replication factor, retention). [cite: 76] [cite_start]All other services explicitly depend on the successful completion of this service. [cite: 77]
#### Service Health Checks
[cite_start]Before any consumer service begins polling for messages, it performs a startup health check. [cite: 78] [cite_start]It connects to the Kafka AdminClient and verifies that all of the topics it needs to subscribe to already exist. [cite: 79] [cite_start]The service will retry this check for up to 60 seconds. [cite: 80] [cite_start]If the topics do not appear, the service will exit with a critical error, preventing it from running in an invalid state. [cite: 81]
#### Idempotent Processing
[cite_start]To ensure data consistency and prevent duplicate calculations from event replays, all calculator services are **idempotent**. [cite: 82] This is achieved by:
1.  [cite_start]Generating a unique ID for each incoming Kafka message (from its topic, partition, and offset). [cite: 83]
2.  [cite_start]Using a shared `processed_events` table in the database. [cite: 84]
3.  [cite_start]Wrapping the business logic in an atomic transaction: the service first checks if the event ID exists in the table. [cite: 85]
4.  [cite_start]If not, it processes the data, saves the results, and inserts the event ID into the table as a single, atomic operation. [cite: 86]
5.  [cite_start]If the event ID already exists, the entire operation is skipped. [cite: 87]
### 1.2 Partition Affinity & Ordering

[cite_start]To guarantee that all events related to a single portfolio are processed in the correct order, events are keyed by **`portfolio_id`**. [cite: 88] [cite_start]This ensures that all messages for a given portfolio land on the same Kafka partition, preventing race conditions and ensuring that downstream consumers receive updates for a specific portfolio sequentially. [cite: 89]
```mermaid
graph TD
    subgraph "API Layer"
        direction LR
        Client[User/Client] -- POST Data --> IngestionService[ingestion_service:8000];
        [cite_start]Client -- GET Data --> QueryService[query-service:8001]; [cite: 90]
    end

    subgraph "Kafka Message Bus"
        RawData((raw_events));
        [cite_start]PersistenceCompleted((persistence_completed)); [cite: 91]
        CalculationsCompleted((calculations_completed));
    end

    subgraph "Data Processing Pipeline"
        IngestionService -- Publishes --> RawData;
        [cite_start]RawData --> PersistenceService[persistence-service]; [cite: 92]
        PersistenceService -- Writes --> DB[(PostgreSQL)];
        PersistenceService -- Publishes --> PersistenceCompleted;

        PersistenceCompleted -- "raw_transactions_completed" --> CostCalculator[cost-calculator-service];
        [cite_start]CostCalculator -- Updates --> DB; [cite: 93]
        CostCalculator -- Publishes --> CalculationsCompleted;
        
        PersistenceCompleted -- "raw_transactions_completed" --> CashflowCalculator[cashflow-calculator-service];
        CashflowCalculator -- Writes --> DB;
        [cite_start]CalculationsCompleted -- "processed_transactions_completed" --> PositionCalculator[position-calculator-service]; [cite: 94]
        PositionCalculator -- Writes --> DB;
        PositionCalculator -- Publishes --> CalculationsCompleted;

        CalculationsCompleted -- "position_history_persisted" --> ValuationCalculator[position-valuation-calculator];
        [cite_start]PersistenceCompleted -- "market_price_persisted" --> ValuationCalculator; [cite: 95]
        ValuationCalculator -- Updates --> DB;
    [cite_start]end [cite: 96]

    subgraph "Data Query Layer"
        [cite_start]QueryService -- Reads --> DB; [cite: 97]
    end
````

## 2\. Core Services

  - [cite\_start]**`ingestion_service`**: A write-only FastAPI application serving as the single entry point for all incoming data (portfolios, instruments, transactions, etc.). [cite: 98] [cite\_start]It validates and publishes raw events to Kafka. [cite: 99]
  - [cite\_start]**`persistence-service`**: A generic consumer responsible for persisting raw data from Kafka to the PostgreSQL database. [cite: 99] [cite\_start]On successful persistence, it publishes a `_completed` event. [cite: 100]
  - [cite\_start]**`query-service`**: A read-only FastAPI application providing access to all processed and calculated data for reporting and analytics. [cite: 100]
  - [cite\_start]**Calculator Services (`services/calculators/`)**: A suite of specialized, idempotent consumers that perform core business logic: [cite: 101]
      - [cite\_start]**`cost-calculator-service`**: Calculates cost basis and realized gains/losses for transactions, supporting dual-currency trades. [cite: 101]
      - [cite\_start]**`cashflow-calculator-service`**: Generates cashflow records from transactions. [cite: 102]
      - [cite\_start]**`position-calculator-service`**: Computes and maintains a historical time series of portfolio positions, including local currency cost basis. [cite: 102]
      - [cite\_start]**`position-valuation-calculator`**: Calculates the market value and unrealized gain/loss of positions using the latest market prices. [cite: 103]
      - [cite\_start]**`timeseries-generator-service`**: Consumes position and cashflow data to generate daily time series records for performance and attribution analysis. [cite: 104]

-----

## 3\. Data Flow & Kafka Topics

[cite\_start]The system relies on a well-defined sequence of events published to Kafka topics. [cite: 105]

  - [cite\_start]**Raw Data Topics**: `raw_portfolios`, `raw_transactions`, `raw_instruments`, `raw_market_prices`, `raw_fx_rates` [cite: 106]
      - [cite\_start]**Published by**: `ingestion_service` [cite: 106]
      - [cite\_start]**Consumed by**: `persistence-service` [cite: 106]
  - [cite\_start]**Persistence Completion Topics**: `raw_transactions_completed`, `market_price_persisted` [cite: 106]
      - [cite\_start]**Published by**: `persistence-service` [cite: 106]
      - [cite\_start]**Consumed by**: Calculator services (`cost-calculator`, `cashflow-calculator`, `position-valuation-calculator`) [cite: 106]
  - [cite\_start]**Calculation Completion Topics**: `processed_transactions_completed`, `position_history_persisted` [cite: 106]
      - [cite\_start]**Published by**: Calculator services (`cost-calculator`, `position-calculator`) [cite: 106]
      - [cite\_start]**Consumed by**: Downstream calculator services (`position-calculator`, `position-valuation-calculator`) [cite: 106]

-----

## 4\. API Endpoints

### [cite\_start]Write API (`ingestion_service` @ `http://localhost:8000`) [cite: 107]

  - [cite\_start]`POST /ingest/portfolios`: Ingests a list of portfolios. [cite: 107]
  - [cite\_start]`POST /ingest/instruments`: Ingests a list of financial instruments. [cite: 108]
  - [cite\_start]`POST /ingest/transactions`: Ingests a list of financial transactions. [cite: 108]
  - [cite\_start]`POST /ingest/market-prices`: Ingests a list of market prices. [cite: 109]
  - [cite\_start]`POST /ingest/fx-rates`: Ingests a list of foreign exchange rates. [cite: 109]
  - [cite\_start]`GET /health`: Health check for the service. [cite: 110]

### [cite\_start]Read API (`query-service` @ `http://localhost:8001`) [cite: 110]

  - [cite\_start]`GET /portfolios/{portfolio_id}/positions`: Retrieves the latest position for each security in a portfolio, including dual-currency valuation. [cite: 110]
  - [cite\_start]`GET /portfolios/{portfolio_id}/transactions`: Retrieves a paginated list of transactions for a portfolio, including dual-currency costs and P\&L. [cite: 111]
  - [cite\_start]`GET /health`: Health check for the service. [cite: 112]

-----

### **New: Sorting and Filtering**

[cite\_start]List endpoints on the `query-service` support advanced sorting and filtering. [cite: 112] [cite\_start]For example, to get transactions sorted by quantity in ascending order: [cite: 113]

```bash
curl "http://localhost:8001/portfolios/EXAMPLE_PORT_01/transactions?sort_by=quantity&sort_order=asc"
```

  - [cite\_start]**`sort_by`**: Field to sort on. [cite: 113] [cite\_start]Allowed values for transactions are `transaction_date`, `quantity`, `price`, `gross_transaction_amount`. [cite: 114]
  - [cite\_start]**`sort_order`**: Direction of sort. [cite: 114] [cite\_start]Can be `asc` (ascending) or `desc` (descending). [cite: 115]

-----

## 5\. Observability

[cite\_start]The system is designed with observability in mind, exposing metrics, health checks, and structured logs to allow for effective monitoring in a production environment. [cite: 115]

### 5.1 Structured Logging

All services output structured JSON logs. [cite\_start]Every log entry is enriched with a `correlation_id` that is propagated through HTTP headers and Kafka messages, allowing for easy tracing of a single request or event flow across multiple services. [cite: 116]

### 5.2 Health Probes

[cite\_start]Services that run background consumers (like the `persistence-service`) expose a web server with health check endpoints, making them compatible with orchestrators like Kubernetes. [cite: 117]

  - [cite\_start]**`persistence-service` @ `http://localhost:8080`**: [cite: 118]
      - [cite\_start]`GET /health/live`: Liveness probe. [cite: 118] [cite\_start]Returns `200 OK` if the service's process is running and responsive. [cite: 119]
      - [cite\_start]`GET /health/ready`: Readiness probe. [cite: 119] [cite\_start]Returns `200 OK` only if the service can successfully connect to its dependencies (PostgreSQL and Kafka). [cite: 120]

### 5.3 Prometheus Metrics

[cite\_start]Services with a web server also expose an endpoint for metrics in the Prometheus format. [cite: 121]

  - [cite\_start]**`persistence-service` @ `http://localhost:8080/metrics`**: [cite: 122]
      - [cite\_start]Provides default metrics for the health-probe API (e.g., `http_requests_total`). [cite: 122]
      - [cite\_start]Provides custom metrics for Kafka consumer performance: [cite: 123]
          - [cite\_start]`events_processed_total`: A counter for successfully processed messages, labeled by topic and consumer group. [cite: 123]
          - [cite\_start]`events_dlqd_total`: A counter for messages that failed all retries and were sent to the Dead-Letter Queue. [cite: 124]
          - [cite\_start]`event_processing_latency_seconds`: A histogram measuring the time taken to process each message. [cite: 125]
  - [cite\_start]**`query-service` @ `http://localhost:8001/metrics`**: [cite: 126]
      - [cite\_start]Provides default metrics for the query API (e.g., `http_requests_total`). [cite: 126]
      - [cite\_start]Provides custom metrics for database performance: [cite: 127]
          - [cite\_start]`db_operation_latency_seconds`: A histogram measuring the time taken to execute repository methods, labeled by repository and method name. [cite: 127]

-----

## 6\. Local Development

### Prerequisites

  - [cite\_start]**Docker Desktop**: Must be installed and running. [cite: 128]
  - [cite\_start]**Python 3.11**: Must be installed and available in your system's PATH. [cite: 129] [cite\_start]You can download it from the [official Python website](https://www.python.org/downloads/release/python-3110/). [cite: 130] [cite\_start]Newer versions may not be compatible with all project dependencies. [cite: 130]

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
    [cite\_start]This command explicitly creates the virtual environment using Python 3.11. [cite: 131] [cite\_start]On Windows with Git Bash, the `py` launcher is the most reliable way to select a specific version. [cite: 132]
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
4.  [cite\_start]**Install All Dependencies**: This single command will install all core tools and then install all local libraries and services in "editable" mode. [cite: 133]
    ```bash
    pip install -r tests/requirements.txt && pip install -e libs/financial-calculator-engine \
            -e libs/portfolio-common \
            -e services/ingestion_service \
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

[cite\_start]The project contains a comprehensive suite of tests to ensure correctness and reliability. [cite: 136]

1.  **Install Test Dependencies**:
    ```bash
    pip install -r tests/requirements.txt
    ```
2.  **Run All Tests (Unit, Integration, E2E)**:
    ```bash
    pytest
    ```
3.  **Run Tests for a Specific Module or File**:
    To run tests for a single part of the application, specify the directory or file path.
    ```bash
    # Run all unit tests for the financial calculator
    pytest tests/unit/libs/financial-calculator-engine/

    # Run a single test file
    pytest tests/unit/services/calculators/position_calculator/core/test_position_logic.py
    ```
4.  **Run Only E2E Tests**:
    [cite\_start]These tests require the full Docker environment to be running. [cite: 138]
    ```bash
    docker compose up -d
    pytest tests/e2e/
    ```
5.  **Generate a Coverage Report**:
    [cite\_start]To measure which lines of code are executed by the tests, run pytest with the `coverage` flags. [cite: 139]
    ```bash
    pytest --cov=src --cov-report=html
    ```
    [cite\_start]Open the `htmlcov/index.html` file in your browser to view the detailed interactive report. [cite: 140]

-----

## 8\. Database Migrations

[cite\_start]Database schema changes are managed by Alembic. [cite: 141]

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
[cite_start]├── alembic/                  # Database migration scripts [cite: 142]
├── docker/
│   └── base/                 # Base Docker image for Python services
[cite_start]├── libs/                     # Shared Python libraries [cite: 142]
[cite_start]│   ├── portfolio-common/     # Common DB models, events, and utilities [cite: 142]
[cite_start]│   └── financial-calculator-engine/ # Core financial calculation logic [cite: 143]
[cite_start]├── services/                 # Individual microservices [cite: 143]
[cite_start]│   ├── ingestion_service/    # The Write API [cite: 143]
[cite_start]│   ├── persistence-service/  # Generic data persistence consumer [cite: 143]
[cite_start]│   ├── query-service/        # The Read API [cite: 143]
[cite_start]│   └── calculators/          # Business logic consumers [cite: 143]
│       ├── cost_calculator_service/
│       ├── cashflow_calculator_service/
│       ├── position_calculator/
[cite_start]│       └── position-valuation-calculator/ [cite: 144]
├── tests/
[cite_start]│   ├── e2e/                  # End-to-end tests for the whole system [cite: 145]
│   ├── integration/
│   └── unit/
[cite_start]├── docker-compose.yml        # Orchestrates all services for local development [cite: 145]
[cite_start]└── README.md                 # This file [cite: 145]
```

-----

## 10\. Full Usage Example

[cite\_start]This example demonstrates the full flow from ingesting a cross-currency trade to querying the final calculated position with dual-currency P\&L. [cite: 146]

1.  [cite\_start]**Start the entire system**: [cite: 147]

    ```bash
    docker compose up --build -d
    ```

    [cite\_start]Wait about a minute for all services to become healthy. [cite: 147]

2.  [cite\_start]**Ingest a USD-based Portfolio**: [cite: 148]

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/portfolios' -H 'Content-Type: application/json' -d '{
    "portfolios": [{"portfolioId": "DUAL_CURRENCY_PORT_01", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DC_CIF", "status": "ACTIVE", "riskExposure":"High", "investmentTimeHorizon":"Long", "portfolioType":"Discretionary", "bookingCenter":"SG"}]
    }'
    ```

3.  **Ingest a EUR-based Instrument (e.g., Daimler)**:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/instruments' -H 'Content-Type: application/json' -d '{
    "instruments": [{"securityId": "SEC_DAI_DE", "name": "Daimler AG", "isin": "DE0007100000", "instrumentCurrency": "EUR", "productType": "Equity"}]
    }'
    ```

4.  [cite\_start]**Ingest FX Rates** for the trade and valuation dates: [cite: 148]

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/fx-rates' -H 'Content-Type: application/json' -d '{
    "fx_rates": [
      {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-10", "rate": "1.10"},
      {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-15", "rate": "1.20"}
    ]
    }'
    ```

5.  **Ingest a BUY Transaction (in EUR)**:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/transactions' -H 'Content-Type: application/json' -d '{
    "transactions": [{"transaction_id": "DC_BUY_01", "portfolio_id": "DUAL_CURRENCY_PORT_01", "instrument_id": "DAI", "security_id": "SEC_DAI_DE", "transaction_date": "2025-08-10T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"}]
    }'
    ```

6.  **Ingest a SELL Transaction (in EUR)**:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/transactions' -H 'Content-type: application/json' -d '{
    "transactions": [{"transaction_id": "DC_SELL_01", "portfolio_id": "DUAL_CURRENCY_PORT_01", "instrument_id": "DAI", "security_id": "SEC_DAI_DE", "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 170, "gross_transaction_amount": 6800, "trade_currency": "EUR", "currency": "EUR"}]
    }'
    ```

7.  **Ingest a Market Price (in EUR)** to value the final position:

    ```bash
    curl -X 'POST' 'http://localhost:8000/ingest/market-prices' -H 'Content-Type: application/json' -d '{
    "market_prices": [{"securityId": "SEC_DAI_DE", "priceDate": "2025-08-15", "price": 180.0, "currency": "EUR"}]
    }'
    ```

8.  [cite\_start]**Wait a few seconds** for all services to process these events. [cite: 151]

9.  **Query the Final Position**:
    [cite\_start]Call the `query-service` to see the final state, including dual-currency valuation. [cite: 152]

    ```bash
    curl http://localhost:8001/portfolios/DUAL_CURRENCY_PORT_01/positions
    ```

    **Expected Response**:

    ```json
    {
      "portfolio_id": "DUAL_CURRENCY_PORT_01",
      "positions": [
        {
          "security_id": "SEC_DAI_DE",
          "quantity": "60.0000000000",
          "instrument_name": "Daimler AG",
          "position_date": "2025-08-15",
          "cost_basis": "9900.0000000000",
          "cost_basis_local": "9000.0000000000",
          "valuation": {
            "market_price": "180.0000000000",
            "market_value": "12960.0000000000",
            "unrealized_gain_loss": "3060.0000000000",
            "market_value_local": "10800.0000000000",
            "unrealized_gain_loss_local": "1800.0000000000"
          }
        }
      ]
    }
    ```

10. **Query Transactions with Realized P\&L**:
    [cite\_start]Call the `query-service` to see the transaction details, including the calculated dual-currency P\&L on the sale. [cite: 155]

    ```bash
    curl http://localhost:8001/portfolios/DUAL_CURRENCY_PORT_01/transactions
    ```

    **Expected Response**:

    ```json
    {
      "portfolio_id": "DUAL_CURRENCY_PORT_01",
      "total": 2,
      "skip": 0,
      "limit": 100,
      "transactions": [
        {
          "transaction_id": "DC_SELL_01",
          "transaction_date": "2025-08-15T10:00:00",
          "transaction_type": "SELL",
          "instrument_id": "DAI",
          "security_id": "SEC_DAI_DE",
          "quantity": "40.0000000000",
          "price": "170.0000000000",
          "gross_transaction_amount": "6800.0000000000",
          "currency": "EUR",
          "net_cost": "-6600.0000000000",
          "realized_gain_loss": "1560.0000000000",
          "net_cost_local": "-6000.0000000000",
          "realized_gain_loss_local": "800.0000000000",
          "transaction_fx_rate": "1.2000000000",
          "cashflow": {
            "amount": "6800.0000000000",
            "currency": "EUR",
            "classification": "INVESTMENT_INFLOW",
            "timing": "EOD",
            "level": "POSITION",
            "calculationType": "NET"
          }
        },
        {
          "transaction_id": "DC_BUY_01",
          "transaction_date": "2025-08-10T10:00:00",
          "transaction_type": "BUY",
          "instrument_id": "DAI",
          "security_id": "SEC_DAI_DE",
          "quantity": "100.0000000000",
          "price": "150.0000000000",
          "gross_transaction_amount": "15000.0000000000",
          "currency": "EUR",
          "net_cost": "16500.0000000000",
          "realized_gain_loss": null,
          "net_cost_local": "15000.0000000000",
          "realized_gain_loss_local": null,
          "transaction_fx_rate": "1.1000000000",
          "cashflow": {
            "amount": "-15000.0000000000",
            "currency": "EUR",
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
