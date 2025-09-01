# Developer's Guide: Position-Level Analytics

This guide provides developers with instructions for understanding and extending the `position_analytics_service`.

## 1. Architecture

The `PositionAnalyticsService` acts as a high-level **orchestrator**. It does not contain complex financial logic itself. Instead, its primary responsibility is to fetch data from multiple sources, trigger calculations in the appropriate engines, and assemble the final, enriched response.

### Concurrent Enrichment

A key feature of the service's design is the use of `asyncio.gather`. After fetching the base list of a portfolio's current positions, it creates a list of asynchronous tasks to enrich each position with the requested analytics (e.g., fetching income, calculating performance). These tasks are then executed concurrently, which significantly reduces the total response time compared to processing each position sequentially.

## 2. Key Dependencies

To build a single `EnrichedPosition` object, the service interacts with multiple underlying components:

* **Repositories:** It calls methods from `PositionRepository`, `CashflowRepository`, `PerformanceRepository`, and `FxRateRepository` to fetch all the necessary raw data.
* **Calculation Engines:** It directly reuses the `performance-calculator-engine` to perform all Time-Weighted Return (TWR) calculations for the `PERFORMANCE` section.

## 3. Extending the Logic (Adding a New Analytic)

To add a new calculated field to the `EnrichedPosition` DTO (e.g., a `risk_contribution` metric):

1.  **Update the DTO:** Add the new field to the `EnrichedPosition` Pydantic model.
    * **File:** `src/services/query_service/app/dtos/position_analytics_dto.py`

2.  **Create the Logic:** Add a new private method to the `PositionAnalyticsService` that contains the logic to calculate the new metric (e.g., `_calculate_risk_contribution`). This method will likely involve calling an existing or new repository method to fetch data.

3.  **Add to Orchestration:** In the main `_enrich_position` method, add the new logic to the `asyncio.gather` call to ensure it runs concurrently with the other enrichment tasks.

    ```python
    # In _enrich_position method:
    enrichment_tasks = {}
    if PositionAnalyticsSection.PERFORMANCE in request.sections:
        enrichment_tasks['performance'] = self._calculate_performance(...)
    
    # Add your new task here
    if "RISK_CONTRIBUTION" in request.sections:
        enrichment_tasks['risk_contribution'] = self._calculate_risk_contribution(...)

    task_results = await asyncio.gather(*enrichment_tasks.values(), ...)
    ```

4.  **Add Tests:** Add unit tests to `tests/unit/services/query_service/services/test_position_analytics_service.py` to verify the new calculation logic and its integration into the main service method.