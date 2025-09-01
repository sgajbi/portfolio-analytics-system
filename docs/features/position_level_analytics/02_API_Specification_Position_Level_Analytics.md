# API Specification: Position-Level Analytics

This document provides the detailed technical specification for the Position-Level Analytics API endpoint.

* **Base URL:** `http://localhost:8001`
* **Error Responses:**
    * `404 Not Found`: Returned if the `{portfolio_id}` does not exist.
    * `422 Unprocessable Entity`: The request body is malformed or fails validation.
    * `500 Internal Server Error`: An unexpected server-side error occurred.

---

## 1. Endpoint

* **Method:** `POST`
* **Path:** `/portfolios/{portfolio_id}/positions-analytics`
* **Description:** Retrieves a list of all positions for a portfolio and enriches each with a configurable set of on-the-fly analytical metrics.

### Request Body

A JSON object specifying the date and the desired analytical sections.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `asOfDate` | string | Yes | The reference date for all calculations (`YYYY-MM-DD`). |
| `sections` | Array[string] | Yes | An array specifying which analytical sections to include. |
| `performanceOptions` | Object | No | If `PERFORMANCE` is in `sections`, this object defines the periods to calculate. |

#### `sections` Array
Must contain one or more of the following string values:
* `"BASE"`
* `"INSTRUMENT_DETAILS"`
* `"VALUATION"`
* `"INCOME"`
* `"PERFORMANCE"`

#### `performanceOptions` Object
| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `periods` | Array[string] | Yes | An array of standard period types. Allowed values: `"MTD"`, `"QTD"`, `"YTD"`, `"ONE_YEAR"`, `"SI"`. |

### Example Request
```json
{
  "asOfDate": "2025-08-31",
  "sections": [
    "BASE",
    "INSTRUMENT_DETAILS",
    "VALUATION",
    "INCOME",
    "PERFORMANCE"
  ],
  "performanceOptions": {
    "periods": ["YTD", "SI"]
  }
}
````

-----

## 2\. Response Body

The response is a JSON object containing the portfolio details and a list of enriched position objects.

### `EnrichedPosition` Object

Each object in the `positions` array will have the following structure:

| Field | Type | Description |
| :--- | :--- | :--- |
| `securityId` | string | The unique identifier for the security. |
| `quantity` | number | The number of shares/units held. |
| `weight` | number | The position's weight as a percentage of the total portfolio market value. |
| `heldSinceDate` | string | The start date of the current continuous holding period (`YYYY-MM-DD`). |
| `instrumentDetails` | Object | (Optional) Contains instrument reference data. |
| `valuation` | Object | (Optional) Contains market value, cost basis, and unrealized P\&L. |
| `income` | Object | (Optional) Contains the total income generated since the `heldSinceDate`. |
| `performance` | Object | (Optional) Contains the TWR for the requested periods. |

### Example Response

```json
{
  "portfolioId": "E2E_REVIEW_01",
  "asOfDate": "2025-08-31",
  "totalMarketValue": 101270.00,
  "positions": [
    {
      "securityId": "SEC_AAPL",
      "quantity": 100.0,
      "weight": 0.158,
      "heldSinceDate": "2025-08-20",
      "instrumentDetails": {
        "name": "Apple Inc.",
        "isin": "US_AAPL_REVIEW",
        "assetClass": "Equity",
        "sector": "Technology",
        "countryOfRisk": "US",
        "currency": "USD"
      },
      "valuation": {
        "marketValue": {
          "local": {"amount": 16000.00, "currency": "USD"},
          "base": {"amount": 16000.00, "currency": "USD"}
        },
        "costBasis": {
          "local": {"amount": 15000.00, "currency": "USD"},
          "base": {"amount": 15000.00, "currency": "USD"}
        },
        "unrealizedPnl": {
          "local": {"amount": 1000.00, "currency": "USD"},
          "base": {"amount": 1000.00, "currency": "USD"}
        }
      },
      "income": {
        "local": {"amount": 120.00, "currency": "USD"},
        "base": {"amount": 120.00, "currency": "USD"}
      },
      "performance": {
        "YTD": {
          "localReturn": 12.80,
          "baseReturn": 12.80
        },
        "SI": {
          "localReturn": 6.67,
          "baseReturn": 6.67
        }
      }
    }
  ]
}
```
