
# Portfolio Analytics System

This system is designed to process financial transactions, calculate portfolio analytics (positions, valuations, performance), and expose them via REST APIs. It follows a modular, event-driven architecture using Kafka, PostgreSQL, and Python microservices, containerized with Docker.

## Table of Contents

1.  [Project Overview](#1-project-overview)
2.  [System Architecture](#2-system-architecture)
3.  [Implemented Services](#3-implemented-services)
4.  [Core Libraries](#4-core-libraries)
5.  [Technology Stack](#5-technology-stack)
6.  [Local Development Setup](#6-local-development-setup)
    * [Prerequisites](#prerequisites)
    * [Initial Setup](#initial-setup)
    * [Database Migrations](#database-migrations-alembic)
    * [Running the System](#running-the-system-with-docker-compose)
7.  [End-to-End Testing](#7-end-to-end-testing)
8.  [Project Structure](#8-project-structure)
9.  [Future Development](#9-future-development)

---

## 1. Project Overview

The Portfolio Analytics System is a scalable, event-driven microservices platform. Its core function is to process raw financial transaction data and build a robust foundation for various portfolio analytics, including real-time position keeping, valuation, and performance measurement.

---

## 2. System Architecture

The system is built around Kafka to ensure loose coupling between services. Transactions are ingested, persisted, and then enriched by a pipeline of consumer services.

```mermaid
graph TD
    subgraph "Event Flow"
        User[User/Client] -- POST /ingest/transaction --> IngestionService[Ingestion Service];
        IngestionService -- Publishes Event --> KafkaRaw[Kafka Topic: raw_transactions];
        KafkaRaw --> PersistenceService[Transaction Persistence Service];
        PersistenceService -- Persists to DB & Publishes Event --> KafkaCompleted[Kafka Topic: raw_transactions_completed];
        KafkaCompleted --> CostCalculator[Cost Calculator Service];
        CostCalculator -- Enriches Data --> DB[(PostgreSQL)];
    end

    subgraph "Core Components"
        CostCalculator -- Uses --> EngineLib[financial-calculator-engine];
        PersistenceService --> DB;
        IngestionService -.-> DB;
    end
````

-----

## 3\. Implemented Services

### `ingestion-service`

  * **Role**: A FastAPI application that acts as the entry point for new transaction data. It receives transaction details via a REST API, validates them, and publishes them as events to the `raw_transactions` Kafka topic.
  * **Technology**: FastAPI, Pydantic, Confluent Kafka Producer.
  * **API Endpoint**: `POST /ingest/transaction`

### `transaction-persistence-service`

  * **Role**: A Kafka consumer that listens to the `raw_transactions` topic. It is responsible for transforming the event data and persisting it into the PostgreSQL `transactions` table. Upon successful persistence, it publishes a new event to the `raw_transactions_completed` topic.
  * **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

### `cost-calculator-service`

  * **Role**: A Kafka consumer that listens to the `raw_transactions_completed` topic. It uses the `financial-calculator-engine` library to calculate cost basis (`gross_cost`, `net_cost`) and `realized_gain_loss`. It then updates the corresponding transaction record in the PostgreSQL database with these calculated values.
  * **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

-----

## 4\. Core Libraries

### `financial-calculator-engine`

  * **Location**: `libs/financial-calculator-engine`
  * **Role**: A self-contained, installable Python library that holds the core business logic for financial calculations. It handles parsing, sorting, and processing transactions to determine cost basis using configurable strategies (FIFO, Average Cost). It is decoupled from any specific service and includes its own unit tests.

-----

## 5\. Technology Stack

  * **Core Language**: Python 3.11
  * **Containerization**: Docker
  * **Orchestration (Local)**: Docker Compose
  * **Message Broker**: Apache Kafka
  * **Database**: PostgreSQL
  * **Database Migrations**: Alembic
  * **API Framework**: FastAPI
  * **Database ORM**: SQLAlchemy
  * **Data Validation**: Pydantic

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
    This command installs the dependencies for all services and the core calculator library in editable mode.

    ```bash
    pip install -e libs/financial-calculator-engine
    pip install python-dotenv alembic psycopg2-binary -r services/ingestion-service/requirements.txt -r services/transaction-persistence-service/requirements.txt -r services/cost-calculator-service/requirements.txt
    ```

### Database Migrations (Alembic)

Database schema changes are managed by Alembic and must be applied manually during local development.

1.  **Start the Database**:
    Before running migrations, the PostgreSQL container must be running.

    ```bash
    docker compose up -d postgres
    ```

2.  **Generate a New Migration** (Only when you change a model in `common/database_models.py`):

    ```bash
    # Ensure your .venv is active
    alembic revision --autogenerate -m "Your descriptive message here"
    ```

3.  **Apply Migrations**:
    To apply all pending migrations to the database, run:

    ```bash
    alembic upgrade head
    ```

### Running the System with Docker Compose

1.  **Build and Start All Services**:
    This command will build the Docker images for all services and start the containers in the background.

    ```bash
    docker compose up --build -d
    ```

2.  **Check Service Status**:
    Wait for all containers to be in a `running` or `healthy` state.

    ```bash
    docker compose ps
    ```

3.  **Stop All Services**:
    To stop and remove all containers, networks, and volumes, run:

    ```bash
    docker compose down -v
    ```

-----

## 7\. End-to-End Testing

After starting all services, you can verify the full pipeline:

1.  **Access the API Docs**: Open [http://localhost:8000/docs](https://www.google.com/search?q=http://localhost:8000/docs) in your browser.
2.  **Ingest a BUY Transaction**: Use the `POST /ingest/transaction` endpoint to send an initial purchase.
3.  **Ingest a SELL Transaction**: Send a second transaction to sell some of the previously purchased asset.
4.  **Verify in Database**: Connect to the database and check the `transactions` table to confirm that both records were saved and that the `gross_cost`, `net_cost`, and `realized_gain_loss` fields have been correctly calculated and populated.
    ```bash
    # Connect to the database
    docker exec -it postgres psql -U user -d portfolio_db

    # Run query
    SELECT transaction_id, gross_cost, net_cost, realized_gain_loss FROM transactions;
    ```

-----

## 8\. Project Structure

```
.
├── libs/
│   └── financial-calculator-engine/  # Core calculation logic as an installable library
│       ├── pyproject.toml
│       ├── src/
│       └── tests/
├── services/
│   ├── cost-calculator-service/      # NEW: Kafka consumer for cost calculations
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── app/
│   ├── ingestion-service/            # FastAPI service for data ingestion
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── app/
│   └── transaction-persistence-service/ # Kafka consumer for data persistence
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── app/
├── alembic/                           # Alembic migration scripts
│   └── versions/
├── common/                            # Shared utilities and data models
├── .env
├── .gitignore
├── docker-compose.yml
├── pyproject.toml                     # Root project file
└── README.md
```

-----

## 9\. Future Development

  * Complete the decoupling of the `common` module into versioned, installable packages.
  * Implement the remaining calculator services (position, valuation, performance).
  * Build the final REST API service to expose the calculated analytics.
  * Integrate monitoring (Prometheus/Grafana) and structured logging.
  * Establish a CI/CD pipeline for automated testing and deployment.

<!-- end list -->
 