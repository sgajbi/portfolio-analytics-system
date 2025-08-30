### RFC 016: Concentration Analytics Engine

  * **Status**: Proposed
  * **Date**: 2025-08-30
  * **Services Affected**: `query-service`, New `concentration-analytics-engine` library
  * **Related RFCs**: RFC 007, RFC 008, RFC 012

-----

## 1\. Summary (TL;DR)

This RFC proposes the creation of a new, on-the-fly **Concentration Analytics Engine**. This feature will provide Client Advisors with critical insights into portfolio risks that are not captured by standard deviation alone, focusing on over-reliance on single entities or small groups of assets.

The engine will be implemented as a new, self-contained library (`concentration-analytics-engine`) and exposed via a new, consolidated endpoint in the `query-service`: `POST /portfolios/{portfolio_id}/concentration`. It will calculate three key types of concentration:

1.  **Issuer Concentration**: Total exposure to a single corporate entity (e.g., Apple Inc.), rolled up to the ultimate parent.
2.  **Counterparty Concentration**: Net unsecured credit risk to a single trading counterparty (e.g., an OTC derivatives provider).
3.  **Bulk (Idiosyncratic) Concentration**: Measures of portfolio diversification, such as Top-N holdings and the Herfindahl-Hirschman Index (HHI).

The calculations will be highly configurable and leverage existing data repositories, ensuring a consistent and integrated experience.

-----

## 2\. Motivation

Diversification is a cornerstone of prudent investment management. While risk metrics like volatility measure overall portfolio price fluctuation, they do not adequately capture the risk of a significant loss resulting from the failure or severe downturn of a single entity. Concentration analytics are essential for:

  * **Identifying Hidden Risks**: Uncovering over-exposure to a single company's debt and equity, or to a single derivatives counterparty.
  * **Enhancing Advisor Oversight**: Providing quantitative data to support recommendations for diversification and risk mitigation.
  * **Improving Client Reporting**: Adding a crucial dimension to portfolio reviews that sophisticated clients expect to see.

-----

## 3\. Architectural Design

The implementation will follow our established pattern of a stateless calculation engine (a new library) orchestrated by a service within the `query-service`.

  * **New `concentration-analytics-engine` Library**: A new library will be created in `src/libs/` to encapsulate all complex concentration logic. It will be pure Python and pandas, containing no I/O operations, ensuring it is stateless, deterministic, and highly testable.
  * **`query-service` Integration**:
      * A new `ConcentrationService` will be added to `query-service`. This service will be responsible for fetching all necessary data from our various repositories (`PositionRepository`, `InstrumentRepository`, etc.).
      * It will then pass this data to the new engine for calculation.
      * Finally, it will format the results into the API response DTO.
  * **Data Sourcing**: The `ConcentrationService` will fetch a superset of all required data in a single, parallelized operation (`asyncio.gather`) to minimize database round-trips. This includes positions, instrument details, and FX rates.

-----

## 4\. Key Methodologies

### 4.1. Issuer Concentration

This measures the total exposure to a single corporate entity, rolled up to its ultimate parent. For a given portfolio, the process is:

1.  Fetch all positions and their market values.
2.  For each position, identify the ultimate parent issuer using an internal hierarchy mapping. For a structured note, the issuer is the bank that wrote the note, not the underlying.
3.  For funds (ETFs, Mutual Funds), apply a "look-through" to the underlying holdings, apportioning the fund's market value to the issuers of its constituents. If look-through data is unavailable, the fund itself is treated as a single issuer.
4.  Aggregate all market values by ultimate parent issuer and express as a percentage of the total portfolio value.

### 4.2. Bulk Concentration

This measures the portfolio's overall level of diversification. We will calculate two standard industry metrics based on position weights ($w\_i$):

  * **Top-N Concentration ($CR\_N$)**: The sum of the weights of the largest N positions (e.g., Top-5, Top-10).
    $$CR_N = \sum_{i=1}^{N} w_{(i)}$$
  * **Herfindahl-Hirschman Index (HHI)**: The sum of the squared weights of all positions. A value approaching 1 indicates a highly concentrated portfolio.
    $$HHI = \sum_{i=1}^{N} w_i^2$$

### 4.3. Counterparty Concentration

This is a more complex measure focused on credit risk from derivatives and cash holdings. For v1, we will defer the complex calculation of Potential Future Exposure (PFE) and focus on a clear, universally applicable metric:

  * **Net Unsecured Exposure**: For each counterparty (e.g., a bank holding a cash deposit), the exposure is the balance held. For OTC derivatives, it is the net positive market value (`max(0, MTM)`), less any collateral posted.

-----

## 5\. API Specification (`query-service`)

A single, consolidated endpoint provides a more efficient and consistent interface than multiple granular endpoints.

  * **Method**: `POST`
  * **Path**: `/portfolios/{portfolio_id}/concentration`

### Request Body

The request allows the client to specify which metrics to compute and to provide key configuration options.

```json
{
  "scope": {
    "as_of_date": "2025-08-30",
    "reporting_currency": "USD"
  },
  "metrics": [
    "ISSUER",
    "BULK"
  ],
  "options": {
    "lookthrough_enabled": true,
    "issuer_top_n": 10,
    "bulk_top_n": [5, 10]
  }
}
```

### Response Body

The response contains a section for each requested metric, including a summary of findings that exceed predefined thresholds.

```json
{
  "scope": {
    "as_of_date": "2025-08-30",
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
    "hhi": 0.18,
    "flag": "WARN"
  }
}
```

-----

## 6\. Implementation Plan

  * **Phase 1: Foundation (Library & Data)**
    1.  Create the new `concentration-analytics-engine` library skeleton.
    2.  Enhance existing repositories in `query-service` to efficiently fetch the required superset of data (e.g., look-through holdings, issuer hierarchies). This may require new repository methods.
  * **Phase 2: Core Logic & API**
    1.  Implement the **Issuer** and **Bulk** concentration logic within the new engine library, complete with comprehensive unit tests.
    2.  Build the `ConcentrationService` and the `POST /concentration` endpoint in `query-service`.
  * **Phase 3: Advanced Features & v1.1**
    1.  Implement the **Counterparty** concentration logic.
    2.  Expand the configuration options (e.g., allowing `face_value` vs. `market_value` for bond exposures).

-----

## 7\. Risks & Mitigations

  * **Data Quality**: The accuracy of concentration analytics, especially with look-through, is highly dependent on the quality of the underlying holdings and issuer hierarchy data.
      * **Mitigation**: The engine will be designed to fail gracefully. If look-through data for a fund is missing or stale, it will fall back to treating the fund as a single issuer and flag this in the response. If an issuer hierarchy is missing, it will use the direct legal entity issuer.
  * **Performance**: Look-through calculations on portfolios with many nested funds can be computationally expensive.
      * **Mitigation**: The engine will enforce a maximum look-through depth (e.g., 3-5 levels) to prevent infinite recursion. All data transformations will be vectorized using pandas/NumPy for performance.