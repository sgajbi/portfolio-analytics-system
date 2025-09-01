
# Developer's Guide: Performance Analytics

This guide provides developers with instructions for understanding and extending the performance analytics features.

## 1. Architecture

The performance calculation logic is split between the `query_service` and the shared `libs` to ensure a clean separation of concerns.

* **`PerformanceService` & `MWRService` (in `query_service`):** These services act as **orchestrators**. Their responsibilities are:
    1.  Parse the incoming API request.
    2.  Resolve the requested time periods into concrete start and end dates.
    3.  Fetch the necessary raw `portfolio_timeseries` data from the `PerformanceRepository`.
    4.  Instantiate and call the appropriate calculation engine.
    5.  Format the engine's output into the final API response DTO.

* **`performance-calculator-engine` & `mwr_calculator` (in `libs`):** These are pure, stateless libraries that contain all the complex financial logic. They know nothing about APIs or databases. They take in a list of time-series data and a configuration, and they return the calculated results. This separation makes the core logic highly portable and easy to unit test in isolation.

## 2. Using the Engines Directly

A developer can use the calculation engines directly for testing or building new features.

**TWR Engine Example:**
```python
from performance_calculator_engine.calculator import PerformanceCalculator

# 1. Define the configuration
config = {
    "metric_basis": "NET",
    "period_type": "EXPLICIT",
    "performance_start_date": "2025-01-01",
    "report_start_date": "2025-08-01",
    "report_end_date": "2025-08-31",
}

# 2. Get the raw daily data (list of dicts)
daily_data = [...] 

# 3. Instantiate and run the calculator
calculator = PerformanceCalculator(config=config)
results_df = calculator.calculate_performance(daily_data)
cumulative_return = results_df.iloc[-1]["final_cumulative_ror_pct"]
````

## 3\. Extending the Logic (Adding a New Period Type)

To add a new standard period type (e.g., `"SIX_MONTH"`):

1.  **Update the DTO:** Add the new literal to the `StandardPeriod` model to allow it in the API request.

      * **File:** `src/services/query_service/app/dtos/performance_dto.py`

    <!-- end list -->

    ```python
    class StandardPeriod(PeriodBase):
        type: Literal["MTD", "QTD", "YTD", "THREE_YEAR", "FIVE_YEAR", "SI", "SIX_MONTH"]
    ```

2.  **Update the Helper Logic:** Add the corresponding logic to the `resolve_period` function in the engine's helper file.

      * **File:** `src/libs/performance-calculator-engine/src/performance_calculator_engine/helpers.py`

    <!-- end list -->

    ```python
    # In resolve_period function
    elif period_type == "SIX_MONTH":
        start_date = as_of_date - relativedelta(months=6) + timedelta(days=1)
    ```

3.  **Add a Unit Test:** Add a test case to `tests/unit/libs/performance-calculator-engine/unit/test_helpers.py` to verify that the new period type resolves to the correct start and end dates.

<!-- end list -->

