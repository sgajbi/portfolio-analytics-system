# API Specification: Risk Analytics

> Migration Notice (RFC 056): As of February 25, 2026, PAS hard-disables this
> endpoint with `410 Gone`. Authoritative risk analytics now belong to PA.
> Use PA APIs instead of PAS for risk metrics.

This document provides the detailed technical specification for the Risk Analytics API endpoint.

## 1. Endpoint

The Risk Analytics API is exposed through a single, powerful endpoint that calculates multiple metrics for multiple time periods in a single request.

* **Method**: `POST`
* **Path**: `/portfolios/{portfolio_id}/risk`
* **Description**: Calculates a suite of on-the-fly risk metrics for a given portfolio.

### Path Parameters

| Parameter      | Type   | Description                               |
|----------------|--------|-------------------------------------------|
| `portfolio_id` | string | **Required**. The unique identifier of the portfolio. |

---

## 2. Request Body

The request body is a JSON object with four main sections: `scope`, `periods`, `metrics`, and `options`.

### 2.1. Top-Level Structure

| Field     | Type          | Required | Description                                                              |
|-----------|---------------|----------|--------------------------------------------------------------------------|
| `scope`   | Object        | Yes      | Defines the overall context for the calculation (e.g., as-of-date).      |
| `periods` | Array[Object] | Yes      | An array defining the time periods for which to calculate metrics.         |
| `metrics` | Array[string] | Yes      | An array of the specific risk metrics to be calculated.                  |
| `options` | Object        | No       | Defines detailed calculation parameters applicable to all metrics. |

### 2.2. `scope` Object

| Field                | Type   | Default | Description                                                                 |
|----------------------|--------|---------|-----------------------------------------------------------------------------|
| `as_of_date`         | string | Today   | The reference date for relative periods like YTD, MTD, etc. Format: `YYYY-MM-DD`. |
| `reporting_currency` | string | `null`  | ISO code for the response currency. Defaults to the portfolio's base currency. |
| `net_or_gross`       | string | "NET"   | Basis for the underlying returns. Must be "NET" or "GROSS".                 |

### 2.3. `periods` Array

This is an array of "Period Objects". Each object must have a `type` field which determines its structure.

**`EXPLICIT` Period**
| Field       | Type   | Required | Description                       |
|-------------|--------|----------|-----------------------------------|
| `type`      | string | Yes      | Must be "EXPLICIT".               |
| `name`      | string | No       | A custom name for the result key. |
| `from_date` | string | Yes      | Start date (`YYYY-MM-DD`).        |
| `to_date`   | string | Yes      | End date (`YYYY-MM-DD`).          |

**`YEAR` Period**
| Field  | Type    | Required | Description                       |
|--------|---------|----------|-----------------------------------|
| `type` | string  | Yes      | Must be "YEAR".                   |
| `name` | string  | No       | A custom name for the result key. |
| `year` | integer | Yes      | The calendar year (e.g., `2024`).  |

**Standard Periods**
| Field  | Type   | Required | Description                                                   |
|--------|--------|----------|---------------------------------------------------------------|
| `type` | string | Yes      | Must be one of: "MTD", "QTD", "YTD", "THREE_YEAR", "FIVE_YEAR", "SI" (Since Inception). |
| `name` | string | No       | A custom name for the result key.                             |

### 2.4. `metrics` Array

A list of strings specifying which metrics to compute.

**Allowed Values**:
`"VOLATILITY"`, `"DRAWDOWN"`, `"SHARPE"`, `"SORTINO"`, `"BETA"`, `"TRACKING_ERROR"`, `"INFORMATION_RATIO"`, `"VAR"`

### 2.5. `options` Object

| Field                     | Type    | Default      | Description                                                                               |
|---------------------------|---------|--------------|-------------------------------------------------------------------------------------------|
| `frequency`               | string  | "DAILY"      | Return frequency. One of: "DAILY", "WEEKLY", "MONTHLY".                                   |
| `annualization_factor`    | integer | `null`       | Overrides default annualization factor (252 for daily, 52 for weekly, 12 for monthly).    |
| `use_log_returns`         | boolean | `false`      | If `true`, use logarithmic returns; otherwise, arithmetic.                                |
| `risk_free_mode`          | string  | "ZERO"       | Mode for Sharpe Ratio's risk-free rate. Must be "ZERO" or "ANNUAL_RATE".                  |
| `risk_free_annual_rate`   | float   | `null`       | The annual risk-free rate (e.g., `0.025` for 2.5%) if mode is "ANNUAL_RATE".               |
| `mar_annual_rate`         | float   | `0.0`        | The Minimum Acceptable Return (annualized) for the Sortino Ratio.                         |
| `benchmark_security_id`   | string  | `null`       | Security ID of the benchmark for Beta, TE, and IR.                                        |
| `var`                     | Object  | (see below)  | A nested object containing parameters for the Value at Risk calculation.                  |

### 2.6. `options.var` Object

| Field                        | Type    | Default      | Description                                                                    |
|------------------------------|---------|--------------|--------------------------------------------------------------------------------|
| `method`                     | string  | "HISTORICAL" | Method for VaR. One of: "HISTORICAL", "GAUSSIAN", "CORNISH_FISHER".             |
| `confidence`                 | float   | `0.99`       | Confidence level for VaR (e.g., `0.99` for 99%).                                 |
| `horizon_days`               | integer | `1`          | Time horizon in days for the VaR calculation.                                  |
| `include_expected_shortfall` | boolean | `true`       | If `true`, also calculates Expected Shortfall (ES/CVaR).                         |

---

## 3. Example Request

```json
{
  "scope": {
    "as_of_date": "2025-08-29",
    "reporting_currency": "USD",
    "net_or_gross": "NET"
  },
  "periods": [
    { "type": "YTD", "name": "YearToDate" },
    { "type": "EXPLICIT", "name": "Last_30_Days", "from_date": "2025-07-30", "to_date": "2025-08-29" }
  ],
  "metrics": [
    "VOLATILITY",
    "SHARPE",
    "DRAWDOWN",
    "VAR"
  ],
  "options": {
    "frequency": "DAILY",
    "risk_free_mode": "ANNUAL_RATE",
    "risk_free_annual_rate": 0.02,
    "var": {
      "method": "HISTORICAL",
      "confidence": 0.99,
      "include_expected_shortfall": true
    }
  }
}
````

-----

## 4\. Response Body

### 4.1. Top-Level Structure

| Field   | Type   | Description                                                      |
|---------|--------|------------------------------------------------------------------|
| `scope` | Object | The `RiskRequestScope` object sent in the request.               |
| `results` | Object | A dictionary where keys are period names and values are `RiskPeriodResult` objects. |

### 4.2. `RiskPeriodResult` Object

| Field        | Type   | Description                                                 |
|--------------|--------|-------------------------------------------------------------|
| `start_date` | string | The calculated start date of the period (`YYYY-MM-DD`).     |
| `end_date`   | string | The calculated end date of the period (`YYYY-MM-DD`).       |
| `metrics`    | Object | A dictionary where keys are metric names and values are `RiskValue` objects. |

### 4.3. `RiskValue` Object

| Field     | Type    | Description                                                                            |
|-----------|---------|----------------------------------------------------------------------------------------|
| `value`   | float   | The calculated value of the metric. `null` if calculation was not possible.            |
| `details` | Object  | Optional. Contains additional data. For Drawdown, it includes `peak_date` and `trough_date`. For VaR, it can include `expected_shortfall`. If an error occurred, it will contain an `error` message. |

-----

## 5\. Example Response

```json
{
  "scope": {
    "as_of_date": "2025-08-29",
    "reporting_currency": "USD",
    "net_or_gross": "NET"
  },
  "results": {
    "YearToDate": {
      "start_date": "2025-01-01",
      "end_date": "2025-08-29",
      "metrics": {
        "VOLATILITY": { "value": 0.1587, "details": null },
        "SHARPE": { "value": 1.25, "details": null },
        "DRAWDOWN": {
          "value": -0.085,
          "details": {
            "peak_date": "2025-03-15",
            "trough_date": "2025-05-20"
          }
        },
        "VAR": {
          "value": 1.98,
          "details": {
            "expected_shortfall": 2.45
          }
        }
      }
    },
    "Last_30_Days": {
      "start_date": "2025-07-30",
      "end_date": "2025-08-29",
      "metrics": {
        "VOLATILITY": { "value": 0.123, "details": null },
        "SHARPE": { "value": 0.98, "details": null },
        "DRAWDOWN": {
          "value": -0.021,
          "details": {
            "peak_date": "2025-08-10",
            "trough_date": "2025-08-15"
          }
        },
        "VAR": {
          "value": 1.55,
          "details": {
            "expected_shortfall": 1.85
          }
        }
      }
    }
  }
}
```

-----

## 6\. Error Responses

  * **`404 Not Found`**: Returned if the `{portfolio_id}` does not exist.
    ```json
    { "detail": "Portfolio RISK_INT_TEST_01 not found" }
    ```
  * **`422 Unprocessable Entity`**: Returned if the request body is malformed or fails Pydantic validation. The body will contain details about the validation error.
  * **`500 Internal Server Error`**: Returned for any unexpected server-side error during calculation.
    ```json
    {
      "error": "Internal Server Error",
      "message": "An unexpected server error occurred during risk calculation.",
      "correlation_id": "QRY:..."
    }
    ```

<!-- end list -->

 
