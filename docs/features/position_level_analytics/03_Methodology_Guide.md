# Methodology Guide: Position-Level Analytics

This guide details the methodologies used by the `PositionAnalyticsService` to calculate the enrichment data for each holding. All calculations are performed on-the-fly and are strictly **epoch-aware** to ensure consistency.

### `held_since_date`
This metric represents the start date of the current, continuous holding period for a security. It is calculated by:
1.  Querying the `position_history` for the security's most recent record where the `quantity` was zero.
2.  Finding the date of the very next transaction after that "zero point." This date is the `held_since_date`.
3.  If a zero-quantity record is never found, the date of the very first transaction for that security is used.

### `total_income`
This metric is the sum of all cash flows classified as `INCOME` (e.g., dividends, interest) that have been received from the `held_since_date` to the request's `as_of_date`. It is calculated in both local and base currencies:
* **Local Income:** A simple sum of the `amount` from all relevant `cashflows` records.
* **Base Income:** Each individual cash flow's `amount` is converted to the portfolio's base currency using the historical FX rate from its specific `cashflow_date`. These converted amounts are then summed.

### `weight`
This is a simple calculation of the position's weight within the total portfolio:
$$
\text{Weight} = \frac{\text{Position Market Value (Base Currency)}}{\text{Total Portfolio Market Value (Base Currency)}}
$$

### Performance (Time-Weighted Return)
Position-level TWR is calculated using the `performance-calculator-engine` on the data from the `position_timeseries` table. The dual-currency calculation is a two-stage process:

1.  **Local Currency Return:** The `performance-calculator-engine` is run on the raw `position_timeseries` data for the requested period. The market values and cash flows in this table are in the instrument's local currency, so the output is the **local currency TWR**.

2.  **Base Currency Return:** To calculate the return in the portfolio's base currency, which correctly includes the impact of FX rate fluctuations:
    * The daily FX rates for the period are fetched.
    * These rates are applied to the daily market values and cash flows of the local currency time-series, creating a new, temporary time-series in the base currency.
    * The `performance-calculator-engine` is run a **second time** on this currency-converted data to produce the **base currency TWR**.