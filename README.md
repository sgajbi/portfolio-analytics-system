It's an excellent idea to keep the `README.md` updated with our progress. This will ensure that the documentation accurately reflects the current state of the project and makes it easier for anyone (including future you\!) to understand and set up the system.

Given our progress, the `README.md` should now clearly describe the project, its architecture, and specifically detail the two services we've implemented so far: `ingestion-service` and `transaction-persistence-service`, along with instructions on how to run them.

Please update your `README.md` file with the following content. This version provides an overview, details the services, and includes setup and running instructions.

````markdown
# Portfolio Analytics System

Welcome to the Portfolio Analytics System! This system is designed to process financial transactions, calculate portfolio analytics (positions, valuations, performance), and expose them via REST APIs. It follows a modular, event-driven architecture using Kafka, PostgreSQL, and Python microservices, containerized with Docker.

## Table of Contents

1.  [Project Overview](#project-overview)
2.  [System Architecture](#system-architecture)
3.  [Current Implemented Services](#current-implemented-services)
    * [Ingestion Service](#ingestion-service)
    * [Transaction Persistence Service](#transaction-persistence-service)
4.  [Technology Stack](#technology-stack)
5.  [Setup and Running Locally with Docker Compose](#setup-and-running-locally-with-docker-compose)
    * [Prerequisites](#prerequisites)
    * [Cloning the Repository](#cloning-the-repository)
    * [Building and Running Services](#building-and-running-services)
    * [Accessing Services](#accessing-services)
    * [Checking Database Data](#checking-database-data)
    * [Stopping Services](#stopping-services)
6.  [Project Structure](#project-structure)
7.  [Future Development](#future-development)

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

## 4\. Technology Stack

  * **Core Languages**: Python 3.11+
  * **Containerization**: Docker
  * **Orchestration (Local)**: Docker Compose
  * **Message Broker**: Apache Kafka (via Confluent Kafka Python client)
  * **Database**: PostgreSQL
  * **API Framework**: FastAPI
  * **Database ORM**: SQLAlchemy
  * **Data Validation**: Pydantic

## 5\. Setup and Running Locally with Docker Compose

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
2.  **At the `psql` prompt, query the `transactions` table**:
    ```sql
    SELECT * FROM transactions;
    ```
    You should see the transactions that you ingested via the Ingestion Service.

### Stopping Services

To stop and remove all running containers, networks, and volumes created by `docker compose`:

```bash
docker compose down -v
```

  * The `-v` flag removes named volumes declared in the `volumes` section of the `docker-compose.yml` file, which is useful for starting fresh.

## 6\. Project Structure

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

## 7\. Future Development

Future work will include:

  * Implementing services for market data ingestion.
  * Developing analytics calculation services (e.g., position keeping, PnL).
  * Creating a REST API layer to expose calculated analytics.
  * Integrating monitoring (Prometheus/Grafana) and logging (ELK stack).
  * Setting up CI/CD pipelines and Kubernetes deployment.

 