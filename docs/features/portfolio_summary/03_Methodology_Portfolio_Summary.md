# Methodology Guide: Portfolio Summary

This document details the financial methodologies and formulas used in the Portfolio Summary API. All calculations are performed on-the-fly, querying the underlying data tables for the portfolio's **current, active epoch** to ensure consistency and data integrity.

---

## 1. Wealth Summary

The wealth summary provides a point-in-time snapshot of the portfolio's total value as of the requested `as_of_date`.

* **Total Market Value**: This is the sum of the `market_value` for all positions held in the portfolio. The calculation uses the single latest `daily_position_snapshot` for each security on or before the `as_of_date`, filtered for the security's currently active `epoch`.

* **Total Cash**: This is a subset of the Total Market Value. It is calculated by summing the `market_value` from the same snapshots, but only for instruments where the `product_type` is 'Cash'.

---

## 2. P&L Summary

The P&L summary explains the change in the portfolio's value over the requested `period`.

* **Realized P&L**: This is the sum of the `realized_gain_loss` column from the `transactions` table for all `SELL` transactions that occurred within the specified period.

* **Unrealized P&L Change**: This measures the change in the paper profit or loss of the holdings. It is calculated as the unrealized P&L at the end of the period minus the unrealized P&L at the start of the period.
    * **Formula**: `(MV_end - Cost_end) - (MV_start - Cost_start)`
    * **Source**: The values are derived by summing the `unrealized_gain_loss` from the latest `daily_position_snapshots` on or before the period's start and end dates, respectively.

* **Net New Money**: This is the net amount of external cash that has flowed into or out of the portfolio. It is the sum of all `cashflows` where `is_portfolio_flow` is `True` and the `classification` is either `CASHFLOW_IN` or `CASHFLOW_OUT`.

* **Total P&L**: The total investment gain or loss for the period.
    * **Formula**: `Realized P&L + Unrealized P&L Change`

---

## 3. Activity & Income Summaries

These sections provide aggregated totals of cashflows within the specified period, filtered by the `classification` field in the `cashflows` table.

* **Income**: Aggregates cashflows classified as `INCOME`. The logic further inspects the original transaction type to differentiate between `DIVIDEND` and `INTEREST`.
* **Activity**: Aggregates all external flows, such as `CASHFLOW_IN` (Deposits), `CASHFLOW_OUT` (Withdrawals), and `EXPENSE` (Fees). It also separately tracks `TRANSFER` flows.

---

## 4. Asset Allocation

Asset allocation is calculated by grouping the `market_value` of the latest position snapshots by various dimensions derived from the `instruments` table.

* **Unclassified Bucket**: For any given dimension, if an instrument has a `NULL` or empty value for that attribute, its market value is automatically grouped into a category named **"Unclassified"**. This provides a clear data quality metric.

* **Dimension-Specific Logic**:
    * **`ASSET_CLASS`**: Sourced directly from `instrument.asset_class`.
    * **`SECTOR`**: Sourced directly from `instrument.sector`. Primarily for Equities.
    * **`CURRENCY`**: Sourced directly from `instrument.currency`.
    * **`COUNTRY_OF_RISK`**: Sourced directly from `instrument.country_of_risk`.
    * **`RATING`**: Sourced directly from `instrument.rating`. Primarily for Fixed Income.
    * **`MATURITY_BUCKET`**: This dimension is calculated dynamically for Fixed Income instruments.
        * **Formula**: `Time to Maturity = instrument.maturity_date - as_of_date`
        * **Buckets**: The resulting duration is mapped to standard buckets: '0-1Y', '1-3Y', '3-5Y', '5-10Y', '10Y+'.