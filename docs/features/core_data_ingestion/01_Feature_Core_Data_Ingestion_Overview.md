# Feature Documentation: Core Data Ingestion

## 1. Summary

The **`ingestion_service`** is the single, authoritative gateway for all write operations into the portfolio analytics system. Its primary responsibility is to provide a secure, validated, and reliable entry point for all raw financial data, including portfolios, instruments, transactions, market prices, foreign exchange (FX) rates, and business dates.

This service functions as a RESTful API that accepts raw data, performs initial validation, and then publishes the data as events to dedicated **Apache Kafka** topics for asynchronous downstream processing. This decoupled, event-driven approach ensures the system is scalable and resilient.

## 2. Key Features

* **Single Write Endpoint:** All data enters the system through this service, ensuring a consistent validation and publication mechanism.
* **Schema Validation:** Leverages Pydantic models to enforce strict, schema-based validation on all incoming data, rejecting malformed requests immediately.
* **Asynchronous Processing:** Publishes valid data to Kafka topics, allowing multiple downstream services to consume events in parallel without blocking the client.
* **End-to-End Traceability:** Every incoming request is assigned a unique `correlation_id`, which is attached to all logs and forwarded as a header on all Kafka messages, enabling comprehensive tracing of a data point's entire lifecycle.
* **Reprocessing Trigger:** Provides a dedicated endpoint to initiate the reprocessing of specific transactions, which is critical for correcting historical data.

## 3. Design Considerations

* **API vs. Operational Tool for Reprocessing:** The service includes a `POST /reprocess/transactions` endpoint. While functional, this places an operational command within the data ingestion API. A more architecturally distinct approach is the command-line script provided in the `tools/` directory (`reprocess_transactions.py`), which is better suited for targeted operational tasks.