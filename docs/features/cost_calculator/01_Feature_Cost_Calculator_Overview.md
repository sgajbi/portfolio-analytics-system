# Feature Documentation: Cost Calculator

## 1. Summary

The **`cost_calculator_service`** is a crucial backend data enrichment service that calculates the **cost basis** of security purchases and the **realized profit and loss (P&L)** on sales. It consumes raw (but persisted) transaction events and produces new, enriched events with these calculated financial figures.

This service ensures that all P&L is calculated accurately, even in complex scenarios involving back-dated trades, by using a **full history recalculation** method for each security. All of its core financial logic is encapsulated in the reusable `financial-calculator-engine` library.

## 2. Key Features

* **Realized P&L Calculation:** Computes the realized gain or loss for every `SELL` transaction based on a configured cost basis methodology.
* **Cost Basis Tracking:** Tracks the cost basis of all open positions using a tax lot accounting system.
* **Full History Recalculation:** For every new transaction involving a security, the service re-fetches all previous transactions for that same security and recalculates its entire cost basis history from the beginning. This guarantees correctness when historical data is inserted out of order.
* **Dual-Currency Support:** Accurately calculates cost and P&L for portfolios that trade securities in currencies different from their base currency, using the appropriate historical FX rates.
* **Configurable Cost Method:** The underlying engine is designed to support multiple cost basis methods, with **First-In, First-Out (FIFO)** being the current implementation.

## 3. Gaps and Design Considerations

* **Incomplete Cost Methodologies:** The `financial-calculator-engine` currently contains a stub for an `AverageCostBasisStrategy`. However, this strategy is not fully implemented or tested for dual-currency scenarios. As of now, the system exclusively supports the **FIFO** method. Completing and enabling other standard methods (Average Cost, LIFO, Specific Lot) would be a significant enhancement.