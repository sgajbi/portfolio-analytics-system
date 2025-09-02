# Developer's Guide: Foundational Data Queries

This guide provides development instructions for the foundational data query endpoints.

## 1. Common Patterns

The service uses standardized FastAPI dependencies to handle common query features like pagination and sorting.

* **File:** `src/services/query_service/app/dependencies.py`
* **Usage:** These dependencies (`pagination_params`, `sorting_params`) can be added to any router to instantly provide consistent pagination and sorting capabilities.

## 2. Adding a New Filter Parameter

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