# API Specification: Portfolio Review

This document provides the detailed technical specification for the Portfolio Review API endpoint.

## 1. Endpoint

* **Method**: `POST`
* **Path**: `/portfolios/{portfolio_id}/review`
* **Description**: Generates a consolidated, multi-section portfolio review report from a single API call, ensuring all data is atomically consistent.

### Path Parameters

| Parameter      | Type   | Description                               |
| -------------- | ------ | ----------------------------------------- |
| `portfolio_id` | string | **Required**. The unique identifier of the portfolio. |

---

## 2. Request Body

The request body is a simple JSON object specifying the date for the report and which sections to include.

### 2.1. Request Schema

| Field        | Type            | Required | Description                                                                                                                              |
| ------------ | --------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `as_of_date` | string          | Yes      | The reference date for all calculations (e.g., holdings, performance periods). Format: `YYYY-MM-DD`.                                         |
| `sections`   | Array[<a href="#reviewsection-enum">ReviewSection</a>] | Yes      | An array of strings specifying which report sections to generate. The order does not affect the response. |

### 2.2. `ReviewSection` Enum

The `sections` array must contain one or more of the following string values:

* `"OVERVIEW"`
* `"ALLOCATION"`
* `"PERFORMANCE"`
* `"RISK_ANALYTICS"`
* `"INCOME_AND_ACTIVITY"`
* `"HOLDINGS"`
* `"TRANSACTIONS"`

---

## 3. Example Request

```json
{
  "as_of_date": "2025-08-30",
  "sections": [
    "OVERVIEW",
    "ALLOCATION",
    "PERFORMANCE",
    "HOLDINGS"
  ]
}
````

-----

## 4\. Response Body

The response is a detailed JSON object with top-level keys for the portfolio scope and each requested section.

  * **`200 OK`**: Returned on a successful report generation.
  * **`404 Not Found`**: Returned if the `{portfolio_id}` does not exist.
  * **`422 Unprocessable Entity`**: Returned if the request body is malformed (e.g., invalid section name).
  * **`500 Internal Server Error`**: Returned for any unexpected server-side error during calculation.

### 4.1. Example Response Payload

```json
{
  "portfolio_id": "PORTF12345",
  "as_of_date": "2025-08-30",
  "overview": {
    "total_market_value": 1250000.50,
    "total_cash": 50000.25,
    "risk_profile": "Growth",
    "portfolio_type": "Discretionary",
    "pnl_summary": {
      "net_new_money": 10000.00,
      "realized_pnl": 5230.10,
      "unrealized_pnl_change": 12345.67,
      "total_pnl": 17575.77
    }
  },
  "allocation": {
    "by_asset_class": [
      { "group": "Equity", "market_value": 900000.00, "weight": 0.72 },
      { "group": "Fixed Income", "market_value": 300000.25, "weight": 0.24 }
    ],
    "by_sector": [
        // ... other allocation breakdowns
    ]
  },
  "performance": {
      // ... full performance response structure
  },
  "holdings": {
    "holdingsByAssetClass": {
      "Equity": [
        { "security_id": "SEC_AAPL", "instrument_name": "Apple Inc.", "quantity": 100, "market_value": 15000.00, "weight": 0.012, "unrealized_pnl": 2500.00 }
      ],
      "Fixed Income": [
        { "security_id": "SEC_BOND", "instrument_name": "US Treasury Bond", "quantity": 10, "market_value": 9800.00, "weight": 0.008, "unrealized_pnl": 300.00 }
      ]
    }
  }
}
```
