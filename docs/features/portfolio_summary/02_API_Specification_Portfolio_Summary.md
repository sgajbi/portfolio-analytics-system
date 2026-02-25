# API Specification: Portfolio Summary

> Migration Notice (RFC 056): As of February 25, 2026, PAS hard-disables this
> endpoint with `410 Gone`. Summary/reporting ownership moved to RAS.
> Use RAS `POST /reports/portfolios/{portfolio_id}/summary`.

This document provides the detailed technical specification for the Portfolio Summary API endpoint.

## 1. Endpoint

The Portfolio Summary API is exposed through a single endpoint that calculates multiple summary sections in a single request.

* **Method**: `POST`
* **Path**: `/portfolios/{portfolio_id}/summary`
* **Description**: Calculates a consolidated, dashboard-style summary of a portfolio's state as of a given date and for a specified period.

### Path Parameters

| Parameter      | Type   | Description                               |
|----------------|--------|-------------------------------------------|
| `portfolio_id` | string | **Required**. The unique identifier of the portfolio. |

---

## 2. Request Body

The request body is a JSON object that specifies the date, period, and the desired sections for the summary.

### 2.1. Top-Level Structure

| Field                   | Type          | Required | Description                                                                 |
|-------------------------|---------------|----------|-----------------------------------------------------------------------------|
| `as_of_date`            | string        | Yes      | The reference date for all point-in-time calculations (e.g., wealth, allocation). Format: `YYYY-MM-DD`. |
| `period`                | Object        | Yes      | An object defining the time period for all historical calculations (e.g., P&L, activity). |
| `sections`              | Array[string] | Yes      | An array of the specific summary sections to be calculated.                 |
| `allocation_dimensions` | Array[string] | No       | If `ALLOCATION` is in `sections`, this specifies the desired breakdowns.    |

### 2.2. `period` Object

This object follows the same structure as the Performance API. It must have a `type` field which determines its structure.

**`EXPLICIT` Period**
| Field       | Type   | Required | Description                |
|-------------|--------|----------|----------------------------|
| `type`      | string | Yes      | Must be "EXPLICIT".        |
| `from_date` | string | Yes      | Start date (`YYYY-MM-DD`). |
| `to_date`   | string | Yes      | End date (`YYYY-MM-DD`).   |

**Standard Periods**
| Field  | Type   | Required | Description                                             |
|--------|--------|----------|---------------------------------------------------------|
| `type` | string | Yes      | Must be one of: "MTD", "QTD", "YTD", "SI" (Since Inception), etc. |

### 2.3. `sections` Array

A list of strings specifying which summary sections to compute.

**Allowed Values**:
`"WEALTH"`, `"ALLOCATION"`, `"PNL"`, `"INCOME"`, `"ACTIVITY"`

### 2.4. `allocation_dimensions` Array

A list of strings specifying which allocation breakdowns to compute. This is only used if `"ALLOCATION"` is present in the `sections` array.

**Allowed Values**:
`"ASSET_CLASS"`, `"CURRENCY"`, `"SECTOR"`, `"COUNTRY_OF_RISK"`, `"MATURITY_BUCKET"`, `"RATING"`

---

## 3. Example Request

```json
{
  "as_of_date": "2025-08-29",
  "period": {
    "type": "YTD"
  },
  "sections": [
    "WEALTH",
    "PNL",
    "ACTIVITY",
    "ALLOCATION"
  ],
  "allocation_dimensions": [
    "ASSET_CLASS",
    "SECTOR"
  ]
}
````

-----

## 4\. Response Body

The response body is a JSON object containing a `scope` object and a key for each requested section.

### 4.1. Top-Level Structure

| Field            | Type   | Description                                                              |
|------------------|--------|--------------------------------------------------------------------------|
| `scope`          | Object | An object confirming the parameters of the calculation.                  |
| `wealth`         | Object | *(Optional)*. Contains the wealth summary. Present if `WEALTH` was requested. |
| `pnlSummary`     | Object | *(Optional)*. Contains the P\&L summary. Present if `PNL` was requested.     |
| `incomeSummary`  | Object | *(Optional)*. Contains the income summary. Present if `INCOME` was requested. |
| `activitySummary`| Object | *(Optional)*. Contains the activity summary. Present if `ACTIVITY` was requested. |
| `allocation`     | Object | *(Optional)*. Contains the allocation breakdowns. Present if `ALLOCATION` was requested. |

### 4.2. Response Section Objects

  * **`scope` Object**:
      * `portfolio_id` (string)
      * `as_of_date` (string, `YYYY-MM-DD`)
      * `period_start_date` (string, `YYYY-MM-DD`)
      * `period_end_date` (string, `YYYY-MM-DD`)
  * **`wealth` Object**:
      * `total_market_value` (number)
      * `total_cash` (number)
  * **`pnlSummary` Object**:
      * `net_new_money` (number)
      * `realized_pnl` (number)
      * `unrealized_pnl_change` (number)
      * `total_pnl` (number)
  * **`incomeSummary` Object**:
      * `total_dividends` (number)
      * `total_interest` (number)
  * **`activitySummary` Object**:
      * `total_deposits` (number)
      * `total_withdrawals` (number)
      * `total_transfers_in` (number)
      * `total_transfers_out` (number)
      * `total_fees` (number)
  * **`allocation` Object**: Contains keys for each requested dimension (e.g., `by_asset_class`). Each key holds an array of `AllocationGroup` objects.
      * **`AllocationGroup` Object**:
          * `group` (string): The name of the group (e.g., "Equity", "Technology", "Unclassified").
          * `market_value` (number)
          * `weight` (float): The weight of the group as a decimal (e.g., 0.72 for 72%).

-----

## 5\. Example Response

```json
{
  "scope": {
    "portfolio_id": "E2E_SUM_PORT_01",
    "as_of_date": "2025-08-29",
    "period_start_date": "2025-01-01",
    "period_end_date": "2025-08-29"
  },
  "wealth": {
    "total_market_value": 1024850.00,
    "total_cash": 754350.00
  },
  "pnlSummary": {
    "net_new_money": 988500.00,
    "realized_pnl": 4000.00,
    "unrealized_pnl_change": 30500.00,
    "total_pnl": 34500.00
  },
  "activitySummary": {
    "total_deposits": 1000000.00,
    "total_withdrawals": -10000.00,
    "total_transfers_in": 15000.00,
    "total_transfers_out": -16500.00,
    "total_fees": -50.00
  },
  "allocation": {
    "by_asset_class": [
      {
        "group": "Cash",
        "market_value": 754350.00,
        "weight": 0.7361
      },
      {
        "group": "Equity",
        "market_value": 270500.00,
        "weight": 0.2639
      }
    ],
    "by_sector": [
      {
        "group": "Technology",
        "market_value": 270500.00,
        "weight": 0.2639
      },
      {
        "group": "Unclassified",
        "market_value": 754350.00,
        "weight": 0.7361
      }
    ]
  }
}
```

-----

## 6\. Error Responses

  * **`404 Not Found`**: Returned if the `{portfolio_id}` does not exist.
  * **`422 Unprocessable Entity`**: Returned if the request body is malformed or fails validation (e.g., invalid section name, incorrect date format).
  * **`500 Internal Server Error`**: Returned for any unexpected server-side error during calculation.

<!-- end list -->


 
