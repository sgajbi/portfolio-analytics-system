# Feature Documentation: Cashflow Calculator

## 1. Summary

The **`cashflow_calculator_service`** is a specialized backend service responsible for translating raw transaction events into standardized, financially significant cash flow records. These records are the primary input for all performance measurement calculations, such as Time-Weighted Return (TWR) and Money-Weighted Return (MWR).

The service operates on a simple, powerful, rule-based system. It consumes transaction events from a Kafka topic and, based on the transaction type (e.g., "BUY", "DIVIDEND", "FEE"), generates a corresponding cash flow record with the correct amount, sign, and classification.

## 2. Key Concepts

### Position Flow vs. Portfolio Flow

A critical distinction made by this service is between a **position flow** and a **portfolio flow**. This is essential for accurate TWR calculations.

* **Position Flow:** A cash flow that affects the value of a specific instrument but does **not** represent new money entering or leaving the portfolio. A `BUY` or `SELL` is a classic example. The cash used to buy a stock is a negative position flow for the cash instrument and a positive position flow for the stock, but the net effect on the total portfolio value (before any market movement) is zero.
* **Portfolio Flow:** A cash flow that represents external money moving into or out of the portfolio, which directly impacts the denominator in a TWR calculation. A `DEPOSIT` or `WITHDRAWAL` is the clearest example. Certain internal events, like `FEE`s, are also correctly treated as portfolio flows as they represent a permanent removal of capital.

## 3. Key Features

* **Rule-Based Classification:** Uses a centralized configuration (`cashflow_config.py`) to map every transaction type to a specific cash flow classification, timing (Beginning-of-Day or End-of-Day), and flow type (position vs. portfolio).
* **Correct Sign Convention:** Automatically applies the correct sign for financial calculations: inflows to the portfolio (e.g., SELL proceeds, DIVIDENDS) are positive, and outflows (e.g., BUYS, FEES) are negative.
* **Epoch-Aware:** The service is fully integrated with the reprocessing engine. It consumes the `epoch` from incoming transaction events and propagates it to the outbound `cashflow_calculated` events, ensuring data consistency during historical recalculations.

## 4. Gaps and Design Considerations

* **Hardcoded Rules:** The cash flow generation rules are currently hardcoded in a Python dictionary. While simple and effective, this means that any change to a rule (e.g., reclassifying a specific fee type) requires a full code deployment. A more flexible, enterprise-grade solution would be to store these rules in a database table, allowing for dynamic updates without a release.