# Developer's Guide: Cost Calculator

This guide provides developers with instructions for understanding, extending, and testing the `cost_calculator_service`.

## 1. Architecture Overview

The cost calculation logic is split into two distinct parts to ensure a clean separation of concerns:

* **`cost_calculator_service`:** This is the microservice itself. Its sole responsibility is orchestration. It contains the Kafka consumer, database repositories, and the logic for fetching and persisting data. It acts as a wrapper around the engine.
* **`financial-calculator-engine`:** This is a pure, stateless library that contains all the complex financial logic. It knows nothing about Kafka or databases. It takes a list of raw transaction data, processes it, and returns a list of enriched transaction objects. This separation makes the core logic highly portable and easy to unit test in isolation.

## 2. Adding Logic for a New Transaction Type

To add support for a new transaction type (e.g., a "GIFT_IN" of securities), follow these steps:

1.  **Update the Enum:** Add the new transaction type to the `TransactionType` enum in the engine.
    * **File:** `src/libs/financial-calculator-engine/src/core/enums/transaction_type.py`

2.  **Create a New Strategy:** In the service's logic file, create a new class that implements the `TransactionCostStrategy` protocol. This class will contain the specific business logic for your new transaction type.
    * **File:** `src/services/calculators/cost_calculator_service/app/logic/cost_calculator.py`

    ```python
    class GiftInStrategy:
        def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
            # Logic to create a new cost lot, similar to TRANSFER_IN
            # ...
            pass
    ```

3.  **Register the Strategy:** In the `CostCalculator` class within the same file, add your new strategy to the `_strategies` dictionary in the constructor, mapping it to the enum value you created.

    ```python
    # In CostCalculator.__init__
    self._strategies: dict[TransactionType, TransactionCostStrategy] = {
        TransactionType.BUY: BuyStrategy(),
        TransactionType.SELL: SellStrategy(),
        # ... existing strategies
        TransactionType.GIFT_IN: GiftInStrategy(), # Add the new strategy here
    }
    ```

## 3. Testing

When adding new logic, ensure you also add corresponding tests:

* **Engine Logic:** Add unit tests for your new strategy's financial calculations in `tests/unit/libs/financial-calculator-engine/unit/test_cost_calculator.py`.
* **Consumer Integration:** If necessary, add tests to `tests/unit/services/calculators/cost_calculator_service/consumer/test_cost_calculator_consumer.py` to verify the consumer's orchestration of the new logic.