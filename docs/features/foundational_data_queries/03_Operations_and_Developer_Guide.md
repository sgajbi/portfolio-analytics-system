# Operations and Developer Guide: Foundational Data Queries

This guide provides operational and development instructions for the foundational data query endpoints.

## 1. For Operations & Support

### Troubleshooting

The foundational `GET` endpoints are a read-through layer for data that has already been processed and persisted by the upstream pipeline. Therefore, issues with these endpoints almost always point to a problem in an upstream service.

* **Symptom:** Data is missing or incorrect when a user calls a `GET` endpoint (e.g., a transaction is missing from the `/transactions` response).
* **Diagnosis:** The issue is **not** in the `query_service`. The `query_service` is correctly showing that the data does not exist in the final database tables.
* **Resolution:** The problem lies in the data pipeline that populates those tables.
    1.  Trace the data point back to the `ingestion_service` using the `correlation_id` to confirm it was received.
    2.  Check the logs of the relevant consumer service (`persistence_service`, `cost_calculator_service`, etc.) for errors related to that `correlation_id`. The data was likely either dropped in a Dead-Letter Queue (DLQ) or is stuck in a retry loop.

## 2. For Developers

### Common Patterns

The service uses standardized FastAPI dependencies to handle common query features like pagination and sorting.

* **File:** `src/services/query_service/app/dependencies.py`
* **Usage:** These dependencies (`pagination_params`, `sorting_params`) can be added to any router to instantly provide consistent pagination and sorting capabilities.

### Adding a New Filter Parameter

Follow these steps to add a new, optional filter parameter to an existing endpoint. Let's use the example of adding a `status` filter to the `GET /portfolios/` endpoint.

1.  **Update the Router:** Add the new query parameter to the endpoint's signature in the router.
    * **File:** `src/services/query_service/app/routers/portfolios.py`
    ```python
    # In get_portfolios function signature:
    status: Optional[str] = Query(None, description="Filter by portfolio status."),
    ```

2.  **Update the Service:** Pass the new parameter from the router layer down to the service layer.
    * **File:** `src/services/query_service/app/services/portfolio_service.py`
    ```python
    # In get_portfolios method signature:
    async def get_portfolios(
        self,
        # ... existing parameters
        status: Optional[str] = None
    ) -> PortfolioQueryResponse:
        # ...
        db_results = await self.repo.get_portfolios(
            # ... existing parameters
            status=status
        )
        # ...
    ```

3.  **Update the Repository:** Add the new filtering logic to the underlying database query in the repository.
    * **File:** `src/services/query_service/app/repositories/portfolio_repository.py`
    ```python
    # In get_portfolios method:
    stmt = select(Portfolio)
    # ... existing filters
    if status:
        stmt = stmt.filter_by(status=status)
    ```