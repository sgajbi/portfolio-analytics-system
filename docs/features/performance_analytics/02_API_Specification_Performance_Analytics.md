
# API Specification: Performance Analytics

> Migration Notice (RFC 056): As of February 25, 2026, lotus-core hard-disables these
> endpoints with `410 Gone`. Authoritative performance analytics now belong to
> lotus-performance. Use lotus-performance APIs instead of lotus-core for TWR/MWR.

This document provides the detailed technical specification for the TWR and MWR API endpoints.

* **Base URL:** `http://localhost:8201`
* **Error Responses:**
    * `404 Not Found`: Returned if the `{portfolio_id}` does not exist.
    * `422 Unprocessable Entity`: The request body is malformed or fails validation.
    * `500 Internal Server Error`: An unexpected server-side error occurred.

---

## 1. Time-Weighted Return (TWR)

* **Method:** `POST`
* **Path:** `/portfolios/{portfolio_id}/performance`
* **Description:** Calculates time-weighted return (TWR) for a portfolio over one or more specified periods, with support for various period types, breakdowns, and currency conversion.

### Request Body

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `scope` | Object | Yes | Defines the overall context for the calculation. |
| `periods` | Array[Object] | Yes | An array defining the time periods for the calculation. |
| `options` | Object | No | Defines options for tailoring the response. |

#### `scope` Object
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `as_of_date` | string | Today | The reference date for relative periods like YTD (`YYYY-MM-DD`). |
| `net_or_gross` | string | "NET" | Basis for the returns. Must be "NET" or "GROSS". |

#### `periods` Array
An array of "Period Objects". Each object must have a `type` field which determines its structure.
* **`EXPLICIT` Period:** `{ "type": "EXPLICIT", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" }`
* **`YEAR` Period:** `{ "type": "YEAR", "year": YYYY }`
* **`Standard` Period:** `{ "type": "YTD" }` (Also supports "MTD", "QTD", "THREE_YEAR", "FIVE_YEAR", "SI")

Any period object can also contain an optional `"name"` and an optional `"breakdown"` (`"DAILY"`, `"WEEKLY"`, `"MONTHLY"`, `"QUARTERLY"`).

#### `options` Object
| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `include_annualized` | boolean | `true` | Include annualized returns for periods over one year. |
| `include_cumulative` | boolean | `true` | Include the total cumulative return for each period. |
| `include_attributes` | boolean | `false` | Include financial attributes (market values, cashflows). |

### Example TWR Request
```json
{
  "scope": {
    "as_of_date": "2025-08-13",
    "net_or_gross": "NET"
  },
  "periods": [
    {"name": "Year to Date", "type": "YTD", "breakdown": "MONTHLY"},
    {"name": "Last Month", "type": "EXPLICIT", "from": "2025-07-01", "to": "2025-07-31"},
    {"type": "THREE_YEAR"}
  ],
  "options": {
    "include_annualized": true,
    "include_cumulative": true,
    "include_attributes": true
  }
}
````

-----

## 2\. Money-Weighted Return (MWR)

  * **Method:** `POST`
  * **Path:** `/portfolios/{portfolio_id}/performance/mwr`
  * **Description:** Calculates money-weighted return (MWR), also known as the Internal Rate of Return (IRR), for a portfolio over one or more specified periods.

### Request Body

The MWR request uses a similar structure but with a simpler set of periods.

#### `periods` Array

  * **`EXPLICIT` Period:** `{ "type": "EXPLICIT", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD" }`
  * **`Standard` Period:** `{ "type": "YTD" }` (Also supports "MTD", "QTD", "SI")

### Example MWR Request

```json
{
  "scope": {
    "as_of_date": "2025-08-24"
  },
  "periods": [
    {"name": "Year to Date", "type": "YTD"},
    {"name": "Custom Period", "type": "EXPLICIT", "from": "2025-07-01", "to": "2025-08-24"}
  ],
  "options": {
    "annualize": true
  }
}
```

```
```
