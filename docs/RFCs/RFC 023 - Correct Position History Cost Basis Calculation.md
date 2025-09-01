# RFC 023: Correct Position History Cost Basis Calculation

* **Status**: Proposed
* **Date**: 2025-09-01

## 1. Summary

A critical data integrity flaw has been identified in the `position_calculator_service`. The service currently uses a proportional (average cost) approximation to reduce a position's cost basis after a `SELL` or `TRANSFER_OUT` transaction. This is logically inconsistent with the precise, FIFO-based Cost of Goods Sold (COGS) calculated by the upstream `cost_calculator_service`.

This discrepancy causes the `cost_basis` in the `position_history` table to drift away from the true cost basis of the remaining tax lots over time, resulting in incorrect data in all downstream services and APIs. This RFC proposes to fix this bug by refactoring the `position_calculator` to use the correct COGS value provided on the transaction event.

## 2. The Flaw

1.  The `cost_calculator_service` correctly calculates the FIFO-based cost of shares sold and records this value in the `net_cost` field of the `processed_transactions_completed` event (e.g., `-4000.00` representing a COGS of $4,000).
2.  The `position_calculator_service` consumes this event but **ignores the `net_cost` field**.
3.  Instead, it calculates its own cost reduction by taking the percentage of shares being sold and applying it to the total cost basis (`new_cost_basis = old_cost_basis * (1 - sold_qty / old_qty)`).
4.  This approximation is only correct if the cost basis is perfectly uniform, which is almost never the case with FIFO accounting.

## 3. Proposed Solution

The fix is to refactor the `calculate_next_position` method in `position_logic.py` to use the authoritative `net_cost` value from the incoming transaction event.

* **File to Modify:** `src/services/calculators/position_calculator/app/core/position_logic.py`

### Logic Change

The logic for `SELL` and `TRANSFER_OUT` transaction types will be changed.

**From (Incorrect Proportional Logic):**
```python
if not quantity.is_zero():
    proportion_of_holding = transaction.quantity / quantity
    cost_basis_reduction = cost_basis * proportion_of_holding
    cost_basis_local_reduction = cost_basis_local * proportion_of_holding
    
    cost_basis -= cost_basis_reduction
    cost_basis_local -= cost_basis_local_reduction

quantity -= transaction.quantity
````

**To (Correct Additive Logic):**

```python
quantity -= transaction.quantity

# transaction.net_cost is negative for a SELL, representing the COGS.
# Adding it to the cost_basis correctly reduces the total cost.
if transaction.net_cost is not None:
    cost_basis += transaction.net_cost
if transaction.net_cost_local is not None:
    cost_basis_local += transaction.net_cost_local
```

### Consequences

  * **Pros:**
      * **Correctness:** The `position_history` table will now be perfectly consistent with the underlying FIFO tax lots.
      * **Simplicity:** The logic becomes simpler and removes an unnecessary, incorrect recalculation.
  * **Cons:**
      * None. This is a direct bug fix.

## 4\. Acceptance Criteria

  * The `calculate_next_position` logic is updated as described.
  * New unit tests are added to `test_position_logic.py` to explicitly verify that the cost basis for a `SELL` is reduced by the `net_cost` amount from the transaction event.
  * All relevant E2E tests pass after the change.

<!-- end list -->
 