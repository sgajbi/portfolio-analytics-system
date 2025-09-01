# Reprocessing Data Model

The Reprocessing Engine relies on a few key database tables to explicitly manage state and version historical data.

## 1. Core State Management Tables

### `position_state`
This is the most critical table in the reprocessing architecture. It acts as the source of truth for the current state of every `(portfolio_id, security_id)` key.

| Column | Type | Description |
| :--- | :--- | :--- |
| `portfolio_id` | `VARCHAR` (PK) | The portfolio's unique identifier. |
| `security_id` | `VARCHAR` (PK) | The security's unique identifier. |
| `epoch` | `INTEGER` | The current version number for the key's history. |
| `watermark_date` | `DATE` | The date up to which calculations are considered complete and correct for the current epoch. |
| `status` | `VARCHAR` | The key's current state. Can be `CURRENT` or `REPROCESSING`. |

### `instrument_reprocessing_state`
This table acts as a temporary, persistent queue for handling back-dated price events.

| Column | Type | Description |
| :--- | :--- | :--- |
| `security_id` | `VARCHAR` (PK) | The security that received a back-dated price. |
| `earliest_impacted_date` | `DATE` | The earliest back-dated price date seen for this security, ensuring the watermark reset is sufficient. |

## 2. Versioned Historical Data

To support epoch fencing and maintain historical integrity, an `epoch` column has been added to all relevant time-series and historical data tables. API queries for this data are designed to join with the `position_state` table to ensure that only records matching the key's *current* epoch are ever returned.

The `epoch` column exists on the following tables:

* `daily_position_snapshots`
* `position_history`
* `portfolio_valuation_jobs`
* `position_timeseries`
* `portfolio_timeseries`
* `cashflows`