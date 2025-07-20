
# Portfolio Analytics System

Welcome to the Portfolio Analytics System! This system is designed to process financial transactions, calculate portfolio analytics (positions, valuations, performance), and expose them via REST APIs. It follows a modular, event-driven architecture using Kafka, PostgreSQL, and Python microservices, containerized with Docker.

## Table of Contents

1.  [Project Overview](#project-overview)
2.  [System Architecture](#system-architecture)
3.  [Current Implemented Services](#current-implemented-services)
    * [Ingestion Service](#ingestion-service)
    * [Transaction Persistence Service](#transaction-persistence-service)
    * [Transaction Cost Calculator Service](#transaction-cost-calculator-service)
4.  [Integrated Calculator Logic](#integrated-calculator-logic)
5.  [Technology Stack](#technology-stack)
6.  [Environment Setup](#environment-setup)
7.  [Setup and Running Locally with Docker Compose](#setup-and-running-locally-with-docker-compose)
    * [Prerequisites](#prerequisites)
    * [Cloning the Repository](#cloning-the-repository)
    * [Building and Running Services](#building-and-running-services)
    * [Accessing Services](#accessing-services)
    * [Checking Database Data](#checking-database-data)
    * [Stopping Services](#stopping-services)
8.  [Database Migrations (Alembic)](#database-migrations-alembic)
9.  [Project Structure](#project-structure)
10. [Future Development](#future-development)

---

## 1. Project Overview

The Portfolio Analytics System is a scalable, event-driven microservices platform. Its core function is to process raw financial transaction data and build a robust foundation for various portfolio analytics, including real-time position keeping, valuation, and performance measurement.

## 2. System Architecture

The system is built around a message broker (Kafka) to ensure loose coupling and high throughput. Transactions flow from an ingestion layer, through Kafka, to a persistence layer, and will eventually feed into analytical services.

```mermaid
graph TD
    User[User/External System] --> IngestionService[Ingestion Service]
    IngestionService -- Publishes Raw Transactions --> Kafka[Kafka Topic: raw_transactions]
    Kafka --> TransactionPersistenceService[Transaction Persistence Service]
    TransactionPersistenceService --> PostgreSQL[PostgreSQL Database]
````

## 3\. Current Implemented Services

### Ingestion Service (`services/ingestion-service`)

  * **Role**: Acts as the entry point for new transaction data. It receives transaction details via a REST API, validates them, and publishes them as events to the `raw_transactions` Kafka topic. It does **not** directly persist data to the database.
  * **Technology**: FastAPI (Python), Confluent Kafka Producer.
  * **API Endpoint**: `POST /ingest/transaction`

### Transaction Persistence Service (`services/transaction-persistence-service`)

  * **Role**: Consumes transaction events from the `raw_transactions` Kafka topic. It is responsible for validating these events, transforming them into a database-ready format, and persisting them into the PostgreSQL database.
  * **Technology**: Python, Confluent Kafka Consumer, SQLAlchemy, PostgreSQL.

### Transaction Cost Calculator Service (`services/transaction-cost-calculator-service`)

  * **Role**: Calculates transaction-related costs and attributes, including cost basis (FIFO/Average Cost) and realized gain/loss. This service now integrates the advanced logic from the `transaction-cost-engine`.
  * **Technology**: FastAPI (Python), Confluent Kafka Consumer, SQLAlchemy, PostgreSQL, Pydantic, integrated core logic from `transaction-cost-engine`.

## 4\. Integrated Calculator Logic

This system now integrates the core calculator logic from the `transaction-cost-engine` project. This allows for advanced cost basis calculations (FIFO, Average Cost) and realized gain/loss computations directly within the `Transaction Cost Calculator Service`. The `transaction-cost-engine` remains a separate, independently runnable API service for isolated testing and ad-hoc usage.

  * **Core Logic Copied**: The essential Python modules (models, enums, and core calculation logic) from `transaction-cost-engine/src/core` and `transaction-cost-engine/src/logic` have been copied into `services/transaction-cost-calculator-service/app/cost_engine/`.
  * **Internal Imports Adjusted**: The import paths within the copied files have been updated to align with the new project structure (`from app.cost_engine.`). The `settings.py` file has also been updated to correctly locate the `.env` file from the root of the `portfolio-analytics-system`.
  * **Common Models Updated**: The shared `Transaction` Pydantic model (`common/models.py`) and SQLAlchemy ORM model (`common/database_models.py`) have been extended to include `net_cost`, `gross_cost`, and `realized_gain_loss` fields, preparing the database schema for these new calculated values. A new Alembic migration has been generated and applied to reflect these schema changes in the database.

## 5\. Technology Stack

  * **Core Languages**: Python 3.11+
  * **Containerization**: Docker
  * **Orchestration (Local)**: Docker Compose
  * **Message Broker**: Apache Kafka (via Confluent Kafka Python client)
  * **Database**: PostgreSQL
  * **API Framework**: FastAPI
  * **Database ORM**: SQLAlchemy
  * **Data Validation**: Pydantic

## 6\. Environment Setup

To get the project running and manage dependencies effectively, follow these steps in your terminal (e.g., Git Bash on Windows, or any terminal on Linux/macOS):

1.  **Create a Python Virtual Environment** (highly recommended for dependency isolation):

    ```bash
    python -m venv .venv
    ```

    This creates a `.venv` folder in your project root containing a new Python installation.

2.  **Activate the Virtual Environment**:

      * **On Windows (Git Bash / MinGW)**:
        ```bash
        source .venv/Scripts/activate
        ```
      * **On Linux / macOS**:
        ```bash
        source .venv/bin/activate
        ```

    You should see `(.venv)` appear at the beginning of your terminal prompt, indicating the virtual environment is active. **Always ensure this is active before installing packages or running Python scripts for this project.**

3.  **Install Dependencies**: Install all project-wide requirements, including `alembic` and necessary database drivers, into your *active* virtual environment.

    ```bash
    pip install -r common/requirements.txt
    pip install alembic sqlalchemy psycopg2-binary # Ensure alembic, sqlalchemy and a PostgreSQL driver are installed
    ```

    (Note: `psycopg2-binary` is specifically for PostgreSQL. If you are using a different database, adjust the driver as needed.)

## 7\. Setup and Running Locally with Docker Compose

This section guides you through setting up and running the core components of the Portfolio Analytics System on your local machine using Docker Compose.

### Prerequisites

  * **Docker Desktop**: Ensure Docker Desktop is installed and running (includes Docker Engine and Docker Compose).

### Cloning the Repository

First, clone the project repository to your local machine:

```bash
git clone [https://github.com/your-username/portfolio-analytics-system.git](https://github.com/your-username/portfolio-analytics-system.git)
cd portfolio-analytics-system
```

### Building and Running Services

Use Docker Compose to build the service images and start all the containers defined in `docker-compose.yml`:

```bash
docker compose build
docker compose up -d
```

  * `docker compose build`: Builds the Docker images for all services.
  * `docker compose up -d`: Starts all services in detached mode (in the background).

Wait for all services to become healthy. You can check their status with `docker compose ps` or monitor logs.

### Accessing Services

Once all containers are up and running:

  * **Ingestion Service (FastAPI)**:
      * Swagger UI: `http://localhost:8000/docs`
      * You can use this UI to send `POST /ingest/transaction` requests.

### Checking Database Data

To verify that transactions are being persisted by the `transaction-persistence-service` into PostgreSQL:

1.  **Access the PostgreSQL container's shell**:
    ```bash
    docker exec -it postgres psql -U user -d portfolio_db
    ```
    *(Note: The container name might be `portfolio-postgres` or just `postgres` depending on your Docker environment. Use `docker ps -a` to confirm the exact name.)*
2.  **At the `psql` prompt, query the `transactions` table**:
    ```sql
    SELECT * FROM transactions;
    ```
    You should see the transactions that you ingested via the Ingestion Service, now including the new cost calculation fields.

### Stopping Services

To stop and remove all running containers, networks, and volumes created by `docker compose`:

```bash
docker compose down -v
```

  * The `-v` flag removes named volumes declared in the `volumes` section of the `docker-compose.yml` file, which is useful for starting fresh.

## 8\. Database Migrations (Alembic)

Alembic is used to manage database schema changes. **Ensure your virtual environment is active** before running these commands.

  * **Ensure Database is Running:** Before generating or applying migrations, ensure your PostgreSQL database is running.
    ```bash
    docker-compose up -d postgres
    # Or to start all services:
    # docker-compose up -d
    ```
  * **Troubleshooting ModuleNotFoundError**: If you encounter `ModuleNotFoundError` when running Alembic, it might be due to Python not finding your project's modules (`common`, etc.). The `alembic/env.py` script has been configured to add the project root to `sys.path` to help resolve this. Ensure your current working directory in the terminal is the project root when running Alembic commands.
  * **Troubleshooting "Can't locate revision"**: If Alembic cannot find a revision, ensure the migration file exists and that the database history (`alembic_version` table) is consistent. If needed in development, you can reset the database history (`DROP TABLE alembic_version;`) and then run `python -m alembic upgrade head` to re-apply all migrations.
  * **Generate a new migration script**:
    After making changes to SQLAlchemy ORM models (e.g., in `common/database_models.py`), use:
    ```bash
    python -m alembic revision --autogenerate -m "Your descriptive message here"
    ```
    *Note*: For `autogenerate` to work from your host machine, `alembic.ini` has been configured to connect to `localhost:5432`, assuming your Docker setup exposes PostgreSQL on that port.
  * **Apply migrations to the database**:
    To apply all pending migrations up to the latest revision (useful after initial setup or updates):
    ```bash
    python -m alembic upgrade head
    ```
    **Important**: Ensure your `DATABASE_URL` environment variable is correctly configured (e.g., in a `.env` file at the project root) for your *application services* when they run inside Docker, and `alembic.ini` has the correct `localhost` URL for host-based Alembic execution.
  * **Current Migration Status**: A new migration script has been generated to add cost calculation fields to the `transactions` table and update the `transaction_costs` table structure. This script has been successfully applied.

## 9\. Project Structure

```
.
├── services/
│   ├── ingestion-service/
│   │   ├── app/
│   │   │   ├── main.py                   # FastAPI app for ingestion
│   │   │   ├── models/                   # Pydantic models for data
│   │   │   │   └── transaction.py
│   │   │   └── database.py               # (Previously for direct DB interaction, now primarily for Alembic setup)
│   │   ├── migrations/                   # Alembic migration scripts
│   │   └── Dockerfile
│   ├── transaction-persistence-service/
│   │   ├── app/
│   │   │   ├── main.py                   # Kafka consumer entry point
│   │   │   ├── consumers/
│   │   │   │   └── transaction_consumer.py # Kafka consumer logic
│   │   │   ├── models/                   # Pydantic models for Kafka events
│   │   │   │   └── transaction_event.py
│   │   │   └── repositories/             # Database interaction logic
│   │   │       └── transaction_db_repo.py
│   │   └── Dockerfile
│   ├── transaction-cost-calculator-service/
│   │   ├── app/
│   │   │   ├── main.py                   # FastAPI app / Kafka consumer entry point
│   │   │   ├── consumers/                # Kafka consumer logic
│   │   │   │   └── transaction_cost_consumer.py
│   │   │   ├── cost_engine/              # Core logic copied from transaction-cost-engine
│   │   │   │   ├── core/
│   │   │   │   │   ├── config/
│   │   │   │   │   ├── enums/
│   │   │   │   │   └── models/
│   │   │   │   └── logic/
│   │   │   ├── fee_calculators.py        # Existing fee calculation (to be integrated/replaced)
│   │   │   ├── models/                   # Schemas for service-specific API/DB (can be refactored)
│   │   │   │   └── ...
│   │   │   └── repositories/             # Database interaction logic (to be adapted)
│   │   │       └── ...
│   │   └── Dockerfile
│   └── ... (other future services)
├── common/
│   ├── __init__.py
│   ├── config.py                         # Centralized configuration variables
│   ├── kafka_utils.py                    # Kafka producer/consumer utilities
│   ├── db_utils.py                       # Database session utilities
│   ├── database_models.py                # SQLAlchemy ORM models (centralized)
│   └── requirements.txt                  # Common Python dependencies
├── .env.example                          # Example environment variables
├── docker-compose.yml                    # Defines and links all services
├── requirements.txt                      # Project-wide Python dependencies
└── README.md                             # Project documentation
```

## 10\. Future Development

Future work will include:

  * Implementing services for market data ingestion.
  * Developing analytics calculation services (e.g., position keeping, PnL) that consume the new `transaction.calculated` events.
  * Creating a REST API layer to expose calculated analytics.
  * Integrating monitoring (Prometheus/Grafana) and logging (ELK stack).
  * Setting up CI/CD pipelines and Kubernetes deployment.

<!-- end list -->

```
```