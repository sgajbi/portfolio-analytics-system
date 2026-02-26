# API Specification: Concentration Analytics

> Migration Notice (RFC 056): As of February 25, 2026, lotus-core hard-disables this
> endpoint with `410 Gone`. Authoritative concentration analytics now belong to
> lotus-performance. Use lotus-performance APIs instead of lotus-core for concentration metrics.

This document provides the detailed technical specification for the Concentration Analytics API endpoint.

## 1. Endpoint

* **Method**: `POST`
* **Path**: `/portfolios/{portfolio_id}/concentration`
* **Description**: Calculates a suite of on-the-fly concentration risk metrics for a given portfolio, ensuring all data is atomically consistent with the portfolio's active data version (epoch).

### Path Parameters

| Parameter      | Type   | Description                               |
| -------------- | ------ | ----------------------------------------- |
| `portfolio_id` | string | **Required**. The unique identifier of the portfolio. |

---

## 2. Request Body

The request body is a JSON object that specifies the scope, desired metrics, and calculation options.

### 2.1. Top-Level Structure

| Field     | Type            | Required | Description                                                    |
|-----------|-----------------|----------|----------------------------------------------------------------|
| `scope`   | Object          | Yes      | Defines the overall context for the calculation.               |
| `metrics` | Array[string]   | Yes      | An array of the specific concentration metrics to calculate.   |
| `options` | Object          | No       | Defines detailed calculation parameters applicable to all metrics. |

### 2.2. `scope` Object

| Field                | Type   | Default | Description                                  |
|----------------------|--------|---------|----------------------------------------------|
| `as_of_date`         | string | -       | **Required**. The reference date for all calculations. Format: `YYYY-MM-DD`. |
| `reporting_currency` | string | "USD"   | The ISO currency code for the response.      |

### 2.3. `metrics` Array

An array of strings specifying which metrics to compute.

**Allowed Values**: `"ISSUER"`, `"BULK"`

### 2.4. `options` Object

| Field                 | Type          | Default    | Description                                                              |
|-----------------------|---------------|------------|--------------------------------------------------------------------------|
| `lookthrough_enabled` | boolean       | `true`     | If `true`, enables look-through for fund holdings in Issuer Concentration. |
| `issuer_top_n`        | integer       | `10`       | The number of top issuer exposures to return.                            |
| `bulk_top_n`          | Array[integer]| `[5, 10]`  | A list of 'N' values for calculating Top-N bulk concentration.           |

---

## 3. Example Request

```json
{
  "scope": {
    "as_of_date": "2025-08-31",
    "reporting_currency": "USD"
  },
  "metrics": [
    "ISSUER",
    "BULK"
  ],
  "options": {
    "lookthrough_enabled": true,
    "issuer_top_n": 5,
    "bulk_top_n": [5, 10]
  }
}
````

-----

## 4\. Response Body

The response is a detailed JSON object containing a `scope` object and keys for each requested metric.

### 4.1. Top-Level Structure

| Field                  | Type   | Description                                                              |
|------------------------|--------|--------------------------------------------------------------------------|
| `scope`                | Object | An object confirming the parameters of the calculation.                  |
| `summary`              | Object | Contains high-level results like total market value and findings.        |
| `issuer_concentration` | Object | *(Optional)*. Present if `ISSUER` was requested.                           |
| `bulk_concentration`   | Object | *(Optional)*. Present if `BULK` was requested.                             |

### 4.2. Example Response Payload

```json
{
  "scope": {
    "as_of_date": "2025-08-31",
    "reporting_currency": "USD"
  },
  "summary": {
    "portfolio_market_value": 12500000.00,
    "findings": [
      { "level": "BREACH", "message": "Issuer 'XYZ Group' at 15.3% exceeds the 10% limit." },
      { "level": "WARN", "message": "Top 10 holdings make up 62% of the portfolio, exceeding the 60% warning threshold." }
    ]
  },
  "issuer_concentration": {
    "top_exposures": [
      {
        "issuer_name": "XYZ Group",
        "exposure": 1912500.00,
        "weight": 0.153,
        "flag": "BREACH"
      }
    ]
  },
  "bulk_concentration": {
    "top_n_weights": {
      "5": 0.48,
      "10": 0.62
    },
    "single_position_weight": 0.18,
    "hhi": 0.18,
    "flag": "WARN"
  }
}
```

-----

## 5\. Error Responses

  * **`404 Not Found`**: Returned if the `{portfolio_id}` does not exist.
  * **`422 Unprocessable Entity`**: Returned if the request body is malformed (e.g., invalid metric name, incorrect data type).
  * **`500 Internal Server Error`**: Returned for any unexpected server-side error during calculation.

<!-- end list -->

 
