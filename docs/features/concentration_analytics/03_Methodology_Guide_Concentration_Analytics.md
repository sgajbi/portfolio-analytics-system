# Methodology Guide: Concentration Analytics

This document details the financial methodologies and formulas used in the Concentration Analytics API. All calculations are performed on-the-fly, querying the underlying data tables for the portfolio's **current, active epoch** to ensure consistency and data integrity.

---

## 1. Issuer Concentration

### 1.1. Definition

Issuer Concentration measures the total exposure of a portfolio to a single corporate entity, rolled up to its ultimate parent. This is crucial for identifying hidden risks, such as holding both the debt and equity of the same parent company.

### 1.2. Method

The calculation follows a multi-step process:

1.  **Fetch Positions**: The service retrieves all latest open positions for the portfolio as of the requested `as_of_date`, ensuring all data belongs to the current active `epoch` for each security.
2.  **Identify Parent Issuer**: For each position, the `ultimate_parent_issuer_id` is retrieved from the `instruments` table. If this field is `NULL`, the system gracefully falls back to using the instrument's name, grouping it under "Unclassified" to highlight potential data quality gaps.
3.  **Aggregate Exposures**: All position market values are grouped by their `ultimate_parent_issuer_id`.
4.  **Calculate Weights**: The total aggregated market value for each parent issuer is divided by the total market value of the portfolio to determine its weight.
5.  **Fund Look-Through (Optional)**: If enabled, the engine will attempt to look through the holdings of any fund (ETF, Mutual Fund) and apportion its market value to the issuers of its underlying constituents. If look-through data is unavailable for a specific fund, the fund itself is treated as a single issuer.

---

## 2. Bulk Concentration

### 2.1. Definition

Bulk Concentration metrics measure the portfolio's overall level of diversification, highlighting over-reliance on a small number of individual holdings regardless of their issuer.

### 2.2. Metrics & Formulas

All bulk metrics are calculated based on the weight ($w_i$) of each individual position in the portfolio.

#### Single-Position Concentration

* **Definition**: The simplest measure of concentration, representing the weight of the single largest position in the portfolio.
* **Formula**:
  $$
  w_{(1)}
  $$

#### Top-N Concentration ($CR_N$)

* **Definition**: The combined weight of the 'N' largest positions in the portfolio. This is commonly calculated for N=5 or N=10.
* **Formula**:
  $$
  CR_N = \sum_{i=1}^{N} w_{(i)}
  $$

#### Herfindahl-Hirschman Index (HHI)

* **Definition**: The sum of the squared weights of all positions in the portfolio. It is a widely accepted measure of market concentration.
* **Interpretation**:
    * A value approaching `1.0` indicates a monopoly (a portfolio with only one holding).
    * A value approaching `0.0` indicates a highly diversified portfolio with many small holdings.
* **Formula**:
  $$
  HHI = \sum_{i=1}^{N} w_i^2
  $$