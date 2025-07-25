# Portfolio Analytics System

This system is designed to process financial transactions, calculate portfolio analytics (positions, valuations, performance), and expose them via REST APIs. It follows a modular, event-driven architecture using Kafka, PostgreSQL, and Python microservices, containerized with Docker.

## Table of Contents

1.  [Project Overview](#1-project-overview)
2.  [System Architecture](#2-system-architecture)
3.  [Implemented Services](#3-implemented-services)
4.  [Kafka Topics](#4-kafka-topics)
5.  [API Endpoints](#5-api-endpoints)
6.  [Local Development Setup](#6-local-development-setup)
7.  [Testing the Endpoints](#7-testing-the-endpoints)

---

## 1. Project Overview

The Portfolio Analytics System is a scalable, event-driven microservices platform. Its core function is to ingest and process raw financial data (transactions, instruments, market prices, FX rates) and build a robust foundation for various portfolio analytics.

---

## 2. System Architecture

The system is built around Kafka to ensure loose coupling between services. Data is ingested, persisted, and then enriched by a pipeline of consumer services.

```mermaid
graph TD
    subgraph "Ingestion & Event Production"
        User[User/Client] -- POST --> IngestionService[Ingestion Service];
        IngestionService -- Publishes Events --> Kafka;
    end

    subgraph "Kafka Topics"
        Kafka --- raw_transactions((raw_transactions));
        Kafka --- instruments((instruments));
        Kafka --- market_prices((market_prices));
        Kafka --- fx_rates((fx_rates));
    end

    subgraph "Event Consumption & Processing"
        raw_transactions --> PersistenceService[Transaction Persistence Service];
        PersistenceService -- Persists to DB & Publishes --> raw_transactions_completed((raw_transactions_completed));
        raw_transactions_completed --> CostCalculator[Cost Calculator Service];
        CostCalculator -- Enriches Data --> DB[(PostgreSQL)];
    end


```` 
## 3. Implemented Services

#### ingestion-service
* **Role**: A FastAPI application that acts as the entry point for new data. It receives details via REST API, validates them, and publishes them as events to the appropriate Kafka topic.
* **Technology**: FastAPI, Pydantic, Confluent Kafka Producer.

#### transaction-persistence-service
* **Role**: A Kafka consumer that listens to `raw_transactions`. It persists transaction data into the PostgreSQL `transactions` table and publishes an event to `raw_transactions_completed` on success.
* **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

#### cost-calculator-service
* **Role**: A Kafka consumer that listens to `raw_transactions_completed`. It uses the `financial-calculator-engine` library to calculate cost basis (`gross_cost`, `net_cost`, `realized_gain_loss`) and updates the transaction record in the database.
* **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

---

## 4. Kafka Topics

* **`raw_transactions`**: Contains raw, unprocessed transaction events as they are ingested.
* **`raw_transactions_completed`**: Events published by the persistence service after a transaction has been successfully saved to the database.
* **`instruments`**: Contains reference data for financial instruments (e.g., stocks, bonds).
* **`market_prices`**: Contains daily closing prices for securities.
* **`fx_rates`**: Contains daily foreign exchange rates between currency pairs.

---

## 5. API Endpoints

All endpoints are served by the `ingestion-service` at `http://localhost:8000`.

* **`POST /ingest/transactions`**: Ingests a list of financial transactions.
* **`POST /ingest/instruments`**: Ingests a list of financial instruments.
* **`POST /ingest/market-prices`**: Ingests a list of market prices.
* **`POST /ingest/fx-rates`**: Ingests a list of foreign exchange rates.
* **`GET /health`**: Health check for the service.

---


## 6\. Local Development Setup

Follow these steps to set up and run the project on your local machine.

### Prerequisites

  * **Docker Desktop**: Ensure it's installed and running.
  * **Python 3.11**: You must have a Python 3.11 interpreter installed locally.

### Initial Setup

1.  **Clone the Repository**:

    ```bash
    git clone <your-repo-url>
    cd portfolio-analytics-system
    ```

2.  **Create `.env` file**:
    Create a `.env` file in the project root by copying the example. This file stores configuration for Docker and local scripts.

    ```bash
    cp .env.example .env
    ```

3.  **Create and Activate Python 3.11 Virtual Environment**:
    *(Use the command specific to your system for running Python 3.11, e.g., `py -3.11` or `python3.11`)*

    ```bash
    # Replace 'py -3.11' with your command if different
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```

4.  **Install All Python Dependencies**:
    This command installs the dependencies for all services and the core calculator library.

    ```bash
    pip install -e libs/financial-calculator-engine
    pip install python-dotenv alembic psycopg2-binary -r services/ingestion-service/requirements.txt -r services/transaction-persistence-service/requirements.txt -r services/cost-calculator-service/requirements.txt
    ```

### Database Migrations (Alembic)

Database schema changes are managed by Alembic. The recommended approach for development is to create one clean, initial migration.

1.  **Clean Up Old Migrations** (if any exist):

    ```bash
    # Ensure your .venv is active
    rm alembic/versions/*.py
    ```

2.  **Start the Database**:

    ```bash
    docker compose up -d postgres
    ```

3.  **Wait for the Database to be Healthy**:
    Run `docker compose ps` and wait for the `postgres` container to show a `(healthy)` status.

4.  **Generate a New Migration**:

    ```bash
    alembic revision --autogenerate -m "Create initial schema"
    ```

5.  **Apply Migrations**:

    ```bash
    alembic upgrade head
    ```

### Running the System with Docker Compose

1.  **Build and Start All Services**:
    This command will build the Docker images and start the containers.

    ```bash
    docker compose up --build -d
    ```

2.  **Check Service Status**:

    ```bash
    docker compose ps
    ```

3.  **Stop All Services**:

    ```bash
    docker compose down -v
    ```

-----

### 7\. Testing the Endpoints

After starting all services, you can verify the full pipeline.

1.  **Access the API Docs**: Open `http://localhost:8000/docs` in your browser.
2.  **Use the "Try it out" feature** for each endpoint with the example payloads below. A successful request will return a `202 Accepted` status code.

#### Ingest Instruments

**`POST /ingest/instruments`**

```json
{
  "instruments": [
    {
      "securityId": "SEC_AAPL",
      "name": "Apple Inc.",
      "isin": "US0378331005",
      "instrumentCurrency": "USD",
      "productType": "Equity"
    }
  ]
}
```

#### Ingest Transactions

**`POST /ingest/transactions`**

```json
{
  "transactions": [
    {
      "transaction_id": "TXN_BUY_001",
      "portfolio_id": "PORT_001",
      "instrument_id": "AAPL",
      "security_id": "SEC_AAPL",
      "transaction_date": "2025-07-20",
      "transaction_type": "BUY",
      "quantity": 10,
      "price": 150.50,
      "gross_transaction_amount": 1505,
      "trade_currency": "USD",
      "currency": "USD"
    }
  ]
}
```

#### Ingest Market Prices

**`POST /ingest/market-prices`**

```json
{
  "market_prices": [
    {
      "securityId": "SEC_AAPL",
      "priceDate": "2025-07-25",
      "price": 152.75,
      "currency": "USD"
    }
  ]
}
```

#### Ingest FX Rates

**`POST /ingest/fx-rates`**

```json
{
  "fx_rates": [
    {
      "fromCurrency": "USD",
      "toCurrency": "SGD",
      "rateDate": "2025-07-25",
      "rate": 1.35
    }
  ]
}
```

```
```