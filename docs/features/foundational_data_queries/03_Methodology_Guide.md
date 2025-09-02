# Methodology Guide: Foundational Data Queries

This guide details the core principles behind the foundational query endpoints.

## 1. Read-Through Layer

The foundational `GET` endpoints in the `query-service` function as a simple, efficient, read-through layer for data that has already been fully processed and persisted by the upstream event-driven pipeline. They do not perform any on-the-fly financial calculations. Their primary purpose is to provide direct, filterable access to the final, authoritative state of core data entities like portfolios, positions, and transactions.

## 2. Epoch-Aware Consistency

The most critical methodology applied to these endpoints is **Epoch-Awareness**. To guarantee data integrity and consistency with all other on-the-fly analytics, any query that retrieves historical or stateful data (such as position history or latest positions) is strictly filtered by the current, active `epoch` for each security.

The repository logic automatically joins with the `position_state` table to ensure that only data from the latest, correct version of an entity's history is ever returned. This prevents stale data from previous, incomplete reprocessing flows from being exposed through the API.