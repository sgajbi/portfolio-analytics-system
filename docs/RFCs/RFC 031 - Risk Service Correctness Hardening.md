# RFC 031 - Risk Service Correctness Hardening

- Date: 2026-02-23
- Services Affected: `query-service`
- Status: Implemented

## Summary

This RFC captures production-hardening fixes to `RiskService` that close functional gaps between API contract and implementation.

## Issues Identified

1. `options.frequency` was accepted by the API but daily returns were always used.
2. `options.use_log_returns` was accepted by the API but ignored in calculations.
3. `options.var.horizon_days` was accepted by the API but not applied to VaR/ES scaling.
4. Missing regression tests made these gaps easy to reintroduce.

## Implemented Changes

1. Added deterministic return resampling to `DAILY`, `WEEKLY`, and `MONTHLY`.
2. Added arithmetic-to-log return conversion for return-based risk metrics.
3. Added square-root-of-time scaling for VaR and Expected Shortfall when `horizon_days > 1`.
4. Kept drawdown on arithmetic returns to preserve wealth-index semantics.
5. Added/expanded unit tests in `tests/unit/services/query_service/services/test_risk_service.py` for:
   - Missing portfolio and empty timeseries
   - Full happy-path metric orchestration
   - Error-path handling
   - Weekly resampling with log-return mode
   - VaR/ES horizon-day scaling

## Risk and Race-Condition Review

1. No direct shared-memory race conditions were found in `RiskService`.
2. A residual data-consistency risk remains because reads can span multiple SQL statements while upstream events continue to update state.
3. Mitigation for next phase: add snapshot-read strategy for request-scoped consistency (for example, transaction-level repeatable read and explicit as-of watermark semantics).

## Validation

1. `make ci-local` passes.
2. Query-service combined coverage remains above gate.
3. `risk_service.py` coverage increased with regression safeguards for the corrected behavior.
