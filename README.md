# Portfolio Analytics System

## Project Overview

The Portfolio Analytics System is a microservices-based application designed to ingest, process, and analyze financial transaction data to provide insights into investment portfolios. It leverages a modern data stack including PostgreSQL for relational data, MongoDB for document-based data, Kafka for real-time data streaming, and FastAPI for API services.

## Architecture

The system is composed of several key microservices and data stores:

* **Ingestion Service (FastAPI)**: Responsible for receiving raw transaction data via a REST API, validating it, and publishing it to Kafka. It also manages the PostgreSQL database schema using Alembic.
* **Transaction Processing Service (Python/Kafka Consumer)**: (Future) Will consume transaction data from Kafka, perform enrichment/validation, and store it in PostgreSQL.
* **Portfolio Management Service (FastAPI)**: (Future) Will provide APIs for managing portfolios and retrieving aggregated data.
* **PostgreSQL**: Relational database used for storing structured transaction data, user information, and aggregated portfolio data.
* **MongoDB**: Document database for storing potentially unstructured or supplementary data (e.g., raw ingestion logs, market data snapshots).
* **Kafka**: Distributed streaming platform used for asynchronous communication between services and handling high-throughput data ingestion.
* **Zookeeper**: Manages Kafka brokers.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

* [Docker Desktop](https://www.docker.com/products/docker-desktop) (or Docker Engine and Docker Compose if on Linux/Server) installed and running.
* Git for cloning the repository.
* Python 3.9+ (for understanding project code, though most will run in Docker).

### Setup and Local Development

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/sgajbi/portfolio-analytics-system.git](https://github.com/sgajbi/portfolio-analytics-system.git)
    cd portfolio-analytics-system
    ```

2.  **Verify Docker Setup:**
    Ensure Docker Desktop is running. You can check its status from the system tray (Windows/macOS) or by running:
    ```bash
    docker info
    ```

3.  **Build Docker Images:**
    Build all service images. This step is crucial after any changes to `Dockerfile`s or `requirements.txt`.
    ```bash
    docker compose build
    ```
    *(If you only changed the Ingestion Service code and not its Dockerfile, `docker compose build ingestion-service` might be faster)*

4.  **Database Migrations (Alembic for PostgreSQL):**
    The `ingestion-service` manages the PostgreSQL schema using Alembic. You need to generate and apply migrations.

    a.  **Ensure `alembic` directory is initialized (if not already):**
        *If you've already run `alembic init` on your host and have the `alembic/` directory, skip this step.*
        ```bash
        docker compose run --rm -e PYTHONPATH=/app ingestion-service bash -c "alembic -c /app/alembic.ini init alembic"
        ```

    b.  **Generate Initial Migration for `transactions` table:**
        This command inspects your SQLAlchemy models (`services/ingestion_service/app/database.py`) and compares them to the current database schema, generating a migration script for any detected differences.
        ```bash
        docker compose run --rm -e PYTHONPATH=/app ingestion-service bash -c "alembic -c /app/alembic.ini revision --autogenerate -m 'create transactions table'"
        ```
        *Verify: After running, check the `alembic/versions/` directory for a new Python file describing the `transactions` table creation.*

    c.  **Apply All Pending Migrations:**
        This will create the `transactions` table in your PostgreSQL database. This step is also integrated into the `ingestion-service` startup command in `docker-compose.yml`.
        ```bash
        docker compose run --rm -e PYTHONPATH=/app ingestion-service bash -c "alembic -c /app/alembic.ini upgrade head"
        ```
        *Note: The `ingestion-service`'s `command` in `docker-compose.yml` automatically runs `alembic upgrade head` on startup.*

5.  **Start All Services:**
    This will bring up all containers defined in `docker-compose.yml` in detached mode.
    ```bash
    docker compose up -d
    ```

6.  **Verify Service Status:**
    Check that all containers are running:
    ```bash
    docker compose ps
    ```
    You can also view logs for a specific service (e.g., `ingestion-service`):
    ```bash
    docker compose logs -f ingestion-service
    ```
    Look for messages indicating successful database connection and FastAPI startup.

### Using the Application

1.  **Access API Documentation (Swagger UI):**
    Open your web browser and navigate to:
    `http://localhost:8000/docs`
    You should see the interactive API documentation for the Ingestion Service.

2.  **Ingest Sample Transaction Data:**
    * In the Swagger UI, expand the `POST /ingest/transaction` endpoint.
    * Click "Try it out".
    * Modify the example `request body` if needed (e.g., change values).
    * Click "Execute".
    * You should receive a `200 OK` response indicating successful ingestion. The data will be published to Kafka and, once the processing service is built, stored in PostgreSQL.

    * To check logs for ingestion-service

    ```
    docker compose logs -f ingestion-service
    ```

3.  **Verify Data in PostgreSQL (Optional):**
    You can connect to the PostgreSQL container to verify the `transactions` table and inserted data:
    ```bash
    docker exec -it postgres psql -U user -d portfolio_db
    ```
    Inside the `psql` prompt:
    ```sql
    \dt -- List tables (should show 'transactions')
    SELECT * FROM transactions; -- View ingested data
    \q -- Exit psql
    ```

4. **Verify Message on Kafka Topic:**
    ```
    docker exec kafka kafka-console-consumer \
  --bootstrap-server kafka:9093 \
  --topic raw_transactions \
  --from-beginning \
  --max-messages 1
    ```

### Stopping Services

To stop and remove all running containers, networks, and volumes:
```bash
docker compose down -v --remove-orphans

