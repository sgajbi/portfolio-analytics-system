
# Portfolio Analytics System

This system provides a comprehensive suite of services for portfolio analytics, including position tracking, valuation, performance calculation, and risk analysis. It is designed as a distributed, event-driven architecture using Kafka for messaging and PostgreSQL for data persistence.

## Table of Contents

- [Architectural Overview](#architectural-overview)
- [System Setup](#system-setup)
- [Running the System](#running-the-system)
- [Running Tests](#running-tests)
- [Verifying the Workflow](#verifying-the-workflow)
- [Code Quality](#code-quality)
- [Tools](#tools)

## Architectural Overview

The system follows a microservices architecture, where each service is responsible for a specific domain. Data flows through the system via Kafka topics, ensuring loose coupling and scalability.

### Core Data Flow

1.  **Ingestion Service**: Receives raw transaction and market data via a REST API and publishes it to Kafka.
2.  **Persistence Service**: Consumes raw data from Kafka and persists it to the PostgreSQL database.
3.  **Calculator Services**:
    * **Position Calculator**: Consumes persisted transactions, calculates position history, and manages reprocessing logic.
    * **Position Valuation Calculator**: Consumes price data and valuation jobs to calculate the market value of positions. It includes two key background tasks:
        * **ValuationScheduler**: Creates backfill valuation jobs, advances watermarks, and creates durable jobs for large-scale price reprocessing events.
        * **ReprocessingWorker**: Consumes the durable reprocessing jobs to fan-out watermark resets in a controlled, scalable manner, mitigating the "Thundering Herd" problem.
    * **Cashflow Calculator**: Calculates cash flows based on transactions.
4.  **Timeseries Generator Service**: Aggregates daily position data into position-level and portfolio-level time series.
5.  **Query Service**: Provides a rich FastAPI interface for all read operations. This includes both fetching foundational data (portfolios, transactions, etc.) and performing complex, on-the-fly analytical calculations such as:
    * **Performance Analytics** (TWR, MWR)
    * **Risk Analytics** (Volatility, Sharpe, VaR, etc.)
    * **Concentration Analytics** (HHI, Issuer Exposure)
    * **Consolidated Reporting** (Portfolio Review)

### Key Architectural Patterns

* **Event-Driven**: Services communicate asynchronously through events, promoting resilience and scalability.
* **Outbox Pattern**: Ensures atomicity between database writes and event publishing, guaranteeing "at-least-once" delivery.
* **Idempotent Consumers**: Consumers are designed to handle duplicate messages gracefully, preventing data corruption.
* **Durable Job Queues**: For high-volume, asynchronous tasks like reprocessing fan-outs, the system uses persistent database tables as durable queues to ensure reliability and control.

## System Setup

Follow these steps to set up the development environment.

### Prerequisites

* Docker and Docker Compose
* Python 3.11+
* Git Bash (on Windows)
* VSCode (recommended)

### Installation

1.  **Clone the Repository**:
    ```bash
    git clone <your-repository-url>
    cd portfolio-analytics-system
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python -m venv .venv
    ```

3.  **Activate the Virtual Environment**:
    ```bash
    source .venv/Scripts/activate
    ```

4.  **Install Dependencies**:
    ```bash
    pip install --upgrade pip
    pip install -e "src/libs/financial-calculator-engine"
    pip install -e "src/libs/performance-calculator-engine"
    pip install -e "src/libs/concentration-analytics-engine"
    pip install -e "src/libs/risk-analytics-engine"
    pip install -e "src/libs/portfolio-common"
    pip install -r src/services/ingestion_service/requirements.txt
    pip install -r src/services/persistence_service/requirements.txt
    pip install -r src/services/calculators/position_calculator/requirements.txt
    pip install -r src/services/calculators/cashflow_calculator_service/requirements.txt
    pip install -r src/services/calculators/cost_calculator_service/requirements.txt
    pip install -r src/services/calculators/position_valuation_calculator/requirements.txt
    pip install -r src/services/timeseries_generator_service/requirements.txt
    pip install -r src/services/query_service/requirements.txt
    pip install -r requirements-dev.txt
    ```

5.  **Set Up Environment Variables**:
    ```bash
    cp .env.example .env
    ```
    Review the `.env` file and ensure the settings are correct for your environment.

## Running the System

1.  **Start Infrastructure**:
    This command starts Kafka, Zookeeper, PostgreSQL, and Prometheus.
    ```bash
    docker compose up -d
    ```

2.  **Set Up Kafka Topics**:
    This tool idempotently creates all necessary Kafka topics.
    ```bash
    python -m tools.kafka_setup
    ```

3.  **Run Database Migrations**:
    Apply all pending database migrations to set up the schema.
    ```bash
    alembic upgrade head
    ```

4.  **Start Services**:
    Open a new terminal for each service to run them concurrently.
    ```bash
    # Terminal 1: Persistence Service
    python -m src.services.persistence_service.app.main

    # Terminal 2: Position Calculator Service
    python -m src.services.calculators.position_calculator.app.main

    # Terminal 3: Position Valuation Calculator Service (includes scheduler and worker)
    python -m src.services.calculators.position_valuation_calculator.app.main

    # Terminal 4: Timeseries Generator Service
    python -m src.services.timeseries_generator_service.app.main

    # Terminal 5: Query Service (API)
    python -m src.services.query_service.app.main

    # Terminal 6: Ingestion Service (API)
    python -m src.services.ingestion_service.app.main
    ```

## Running Tests

To run the full suite of unit and integration tests:

```bash
pytest
````

To run tests for a specific directory:

```bash
pytest tests/unit/
pytest tests/integration/
```

To get a coverage report:

```bash
pytest --cov=src
```

## Verifying the Workflow

1.  **Ingest Data**:
    Use the `ingest_data.py` tool to load sample data into the system.

    ```bash
    python -m tools.ingest_data --all
    ```

2.  **Query the API**:
    Once the services have processed the data, you can query the `query-service` API endpoints.

      * API Docs: `http://localhost:8081/docs`

3.  **Check the Database**:
    You can connect to the PostgreSQL database to verify the state of the data.

    ```bash
    docker compose exec postgres psql -U user -d portfolio_db
    ```

    Useful queries:

    ```sql
    -- Check position watermarks
    SELECT * FROM position_state WHERE portfolio_id = 'PORT001';

    -- Check for any pending reprocessing jobs
    SELECT * FROM reprocessing_jobs WHERE status = 'PENDING';

    -- View the latest daily snapshots
    SELECT * FROM daily_position_snapshots WHERE portfolio_id = 'PORT001' ORDER BY date DESC LIMIT 10;
    ```

## Code Quality

This project uses `black` for formatting and `ruff` for linting.

```bash
# Format code
black .
# Lint code
ruff check .
```

## Tools

The `tools/` directory contains helpful scripts for development:

  * `kafka_setup.py`: Creates Kafka topics.
  * `ingest_data.py`: Ingests sample data.
  * `dlq_replayer.py`: Replays messages from a Dead Letter Queue.
  * `reprocess_tool.py`: Triggers reprocessing for specific transactions.

<!-- end list -->

 

 