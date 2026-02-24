# RFC 049 - PAS Core Snapshot Analytics De-Ownership and PA Input Contract

## 1. Problem Statement
PAS `core-snapshot` currently allows `PERFORMANCE` and `RISK_ANALYTICS` sections. This blurs service ownership and duplicates analytics responsibility with PA.

## 2. Decision
- PAS remains system-of-record for portfolio ledger, transactions, positions, valuation, and time-series.
- PA is the analytics owner for performance and advanced analytics.
- PAS `core-snapshot` contract will no longer serve analytics-owned sections (`PERFORMANCE`, `RISK_ANALYTICS`).
- PAS introduces a raw integration contract for PA: `POST /integration/portfolios/{portfolio_id}/performance-input`.

## 3. Contract Changes
- `core-snapshot` governance filters analytics sections and emits warning `ANALYTICS_SECTIONS_DELEGATED_TO_PA` (or rejects in strict mode).
- New endpoint returns raw valuation points:
  - `perfDate`, `beginMv`, `bodCf`, `eodCf`, `mgmtFees`, `endMv`
  - plus `performanceStartDate`, `portfolioId`, `baseCurrency`.

## 4. Architectural Impact
- Clear separation of concerns:
  - PAS: data processing + standardized serving.
  - PA: analytics computation and analytics APIs.
- BFF/UI remain stable while analytics ownership is moved to PA.

## 5. Risks and Trade-Offs
- Existing consumers requesting analytics sections from `core-snapshot` may see filtered sections.
- Transitional complexity while all consumers adopt PA-based analytics paths.

## 6. Implementation Plan
1. Add performance-input endpoint and DTOs in PAS integration contract.
2. Enforce analytics section de-ownership in `core-snapshot` governance.
3. Update capability metadata to advertise raw performance input contract instead of PAS baseline analytics.
4. Update downstream consumers (PA/BFF) and tests.

