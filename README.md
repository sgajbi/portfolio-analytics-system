
# Portfolio Analytics System

This system is designed to process financial transactions, calculate portfolio analytics (positions, valuations, performance), and expose them via REST APIs. It follows a modular, event-driven architecture using Kafka, PostgreSQL, and Python microservices, containerized with Docker.

## Table of Contents

1.  [Project Overview](#1-project-overview)
2.  [System Architecture](#2-system-architecture)
3.  [Implemented Services](#3-implemented-services)
4.  [Kafka Topics](#4-kafka-topics)
5.  [API Endpoints](#5-api-endpoints)
6.  [Local Development Setup](#6-local-development-setup)
7.  [Running Services Locally](#7-running-services-locally)
8.  [Testing the Endpoints](#8-testing-the-endpoints)

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
        raw_transactions --> PersistenceService[Persistence Service];
        instruments --> PersistenceService;
        market_prices --> PersistenceService;
        fx_rates --> PersistenceService;
        PersistenceService -- Persists to DB --> DB[(PostgreSQL)];
        
        # This part of the flow will be updated later
        subgraph "Future: Enrichment"
          direction LR
          DB -- "raw_transactions_completed Event" --> CostCalculator[Cost Calculator Service];
          CostCalculator -- Enriches Data --> DB;
        end
    end
````

## 3\. Implemented Services

#### `ingestion-service`

  * **Role**: A FastAPI application that acts as the entry point for new data. It receives details via REST API, validates them, and publishes them as events to the appropriate Kafka topic.
  * **Technology**: FastAPI, Pydantic, Confluent Kafka Producer.

#### `persistence-service`

  * **Role**: A generic Kafka consumer service that listens to multiple topics (`raw_transactions`, `instruments`, `market_prices`, `fx_rates`). It validates each event and persists the data to the appropriate table in PostgreSQL.
  * **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, Alembic, PostgreSQL.

#### `cost-calculator-service`

  * **Role**: A Kafka consumer that listens for events indicating a transaction has been persisted. It then uses the `financial-calculator-engine` library to calculate cost basis and updates the transaction record in the database.
  * **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

-----

## 4\. Kafka Topics

  * **`raw_transactions`**: Contains raw, unprocessed transaction events.
  * **`instruments`**: Contains reference data for financial instruments.
  * **`market_prices`**: Contains daily closing prices for securities.
  * **`fx_rates`**: Contains daily foreign exchange rates.
  * **`raw_transactions_completed`**: Events published after a transaction has been successfully saved to the database.

-----

## 5\. API Endpoints

All endpoints are served by the `ingestion-service` at `http://localhost:8000`.

  * **`POST /ingest/transactions`**: Ingests a list of financial transactions.
  * **`POST /ingest/instruments`**: Ingests a list of financial instruments.
  * **`POST /ingest/market-prices`**: Ingests a list of market prices.
  * **`POST /ingest/fx-rates`**: Ingests a list of foreign exchange rates.
  * **`GET /health`**: Health check for the service.

-----

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
    ```bash
    cp .env.example .env
    ```
3.  **Create and Activate Python 3.11 Virtual Environment**:
    ```bash
    py -3.11 -m venv .venv
    source .venv/Scripts/activate
    ```
4.  **Install All Python Dependencies**:
    ```bash
    pip install -e libs/financial-calculator-engine -e libs/portfolio-common
    pip install -r services/ingestion-service/requirements.txt -r services/persistence-service/requirements.txt -r services/cost-calculator-service/requirements.txt
    ```

### Database Migrations (Alembic)

1.  **Start the Database**:
    ```bash
    docker compose up -d postgres
    ```
2.  **Generate a New Migration** (only when changing models):
    ```bash
    alembic revision --autogenerate -m "a descriptive message"
    ```
3.  **Apply Migrations**:
    ```bash
    alembic upgrade head
    ```

### Running the System with Docker Compose

1.  **Build and Start All Services**:
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

## 7\. Running Services Locally

To run a specific service for development, use the `python -m` command from the project root after ensuring your venv is active and dependencies are installed.

### Running the Persistence Service

```bash
python -m services.persistence-service.app.main
```

-----

## 8\. Testing the Endpoints

After starting all services with Docker Compose, you can use the "Try it out" feature in the API docs at `http://localhost:8000/docs` with the example payloads.

````
