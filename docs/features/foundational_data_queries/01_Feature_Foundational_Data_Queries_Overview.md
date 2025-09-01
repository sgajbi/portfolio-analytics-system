# Feature Documentation: Foundational Data Queries

## 1. Summary

In addition to its advanced, on-the-fly analytical APIs, the `query_service` provides a suite of simple and efficient RESTful `GET` endpoints for retrieving the core, persisted data entities of the system. These endpoints serve as the primary mechanism for fetching raw, foundational data.

They are the building blocks for user interfaces, external system integrations, and operational tooling, providing direct access to the final, processed state of all key financial data.

## 2. Key Features

* **Comprehensive Data Access:** Provides dedicated endpoints to query all major entities:
    * Portfolios
    * Positions (latest and historical)
    * Transactions
    * Instruments
    * Market Prices
    * Foreign Exchange (FX) Rates
* **Rich Filtering:** Most endpoints support a rich set of query parameters to filter results based on entity-specific attributes (e.g., filter transactions by `security_id` or portfolios by `cif_id`).
* **Standardized Pagination and Sorting:** Endpoints that return lists of data (like transactions and instruments) support standardized query parameters (`skip`, `limit`, `sort_by`, `sort_order`) for easy implementation of paginated UI components.
* **Epoch-Aware Consistency:** All queries that return historical or stateful data (especially positions) are fully **epoch-aware**. The repository logic automatically joins with the `position_state` table to ensure that only data from the latest, correct version of an entity's history is ever returned.