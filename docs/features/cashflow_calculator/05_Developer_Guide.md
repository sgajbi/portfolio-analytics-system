# Developer's Guide: Cashflow Calculator

This guide provides developers with instructions for understanding and extending the `cashflow_calculator_service`.

## 1. Architecture Overview

The `cashflow_calculator_service` is designed to be extremely simple and maintainable. It has two main parts:

* **`TransactionConsumer`:** The Kafka consumer that subscribes to `raw_transactions_completed` events. Its primary job is to look up the correct rule for the incoming transaction type and pass it to the logic layer.
* **`cashflow_config.py`:** This file contains the core of the service's business logic. It holds a simple dictionary (`CASHFLOW_CONFIG`) that declaratively maps transaction types to their corresponding cash flow attributes.

The philosophy of this service is to keep all business rules declarative and centralized in the configuration file, making the system easy to understand and modify.

## 2. Adding a Rule for a New Transaction Type

To add support for a new transaction type (e.g., a "MANAGEMENT_FEE"), follow these steps:

1.  **Verify Transaction Type:** Ensure the new transaction type exists in the `TransactionType` enum.
    * **File:** `src/libs/financial-calculator-engine/src/core/enums/transaction_type.py`

2.  **Add the New Rule:** Add a new entry to the `CASHFLOW_CONFIG` dictionary. This is the only code change required in the service itself.
    * **File:** `src/services/calculators/cashflow_calculator_service/app/core/cashflow_config.py`

    ```python
    # In CASHFLOW_CONFIG dictionary:
    "MANAGEMENT_FEE": CashflowRule(
        classification=CashflowClassification.EXPENSE,
        timing=CashflowTiming.EOD,
        is_position_flow=False, # Mgmt fees are not tied to a single position
        is_portfolio_flow=True   # It is an external outflow of capital
    ),
    ```

3.  **Add a Unit Test:** To ensure your new rule behaves as expected, add a new test case to the logic test suite.
    * **File:** `tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py`

    ```python
    def test_calculate_management_fee_transaction(base_transaction_event: TransactionEvent):
        """A MANAGEMENT_FEE is a negative cashflow (outflow)."""
        event = base_transaction_event
        event.transaction_type = "MANAGEMENT_FEE"
        rule = get_rule_for_transaction("MANAGEMENT_FEE")
        assert rule is not None
        cashflow = CashflowLogic.calculate(event, rule)
        assert cashflow.amount < 0
        assert cashflow.is_position_flow is False
        assert cashflow.is_portfolio_flow is True
    ```

## 3. Testing

To run the unit tests specifically for the cashflow logic, use the following command from the project root:
```bash
pytest tests/unit/services/calculators/cashflow_calculator_service/unit/core/test_cashflow_logic.py