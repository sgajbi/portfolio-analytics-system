# RFC 035 - PAS PA DPM Responsibility and Integration Contract

- Date: 2026-02-23
- Services Affected: `portfolio-analytics-system`, `performanceAnalytics`, `dpm-rebalance-engine`, UI, BFF
- Status: Proposed (with PAS Phase 1 implemented)

## Summary

Define non-overlapping responsibilities and integration contracts across PAS, PA, and DPM so the suite behaves as a coherent end-to-end platform.

## Responsibility Boundaries

1. PAS (Core Platform)
   - System of record for portfolios, positions, transactions, instruments, market data.
   - Processing engine for persistence, valuation, cashflow, timeseries generation.
   - Canonical API source for foundational and support/lineage data.
2. PA (Advanced Analytics)
   - Higher-order analytics: performance attribution, advanced risk, benchmark analytics, model overlays.
   - Consumes PAS data/outputs; does not duplicate PAS ingestion/persistence pipelines.
3. DPM (Advisory and Discretionary Workflows)
   - Construction, recommendation, optimization, and rebalance workflows.
   - Can run from direct portfolio input or PAS-retrieved portfolio state.
4. UI/BFF
   - Unified operator experience.
   - Orchestrates calls across PAS/PA/DPM and enforces presentation contracts.

## Integration Patterns

1. Direct input pattern
   - DPM/PA endpoints may accept portfolio payloads directly for simulation and what-if workflows.
2. PAS-connected pattern
   - DPM/PA use portfolio identifiers and fetch canonical state from PAS APIs.
3. Upload pattern (UI)
   - UI supports manual and file-driven upload of core entities to PAS ingestion APIs.

## PAS Phase 1 Implemented

1. Added `POST /ingest/portfolio-bundle` to support single-request upload of mixed portfolio data:
   - business dates
   - portfolios
   - instruments
   - transactions
   - market prices
   - FX rates
2. Maintains existing PAS downstream event topics and processing flows.
3. Designed for UI form + file upload onboarding.

## Non-Overlap Guardrails

1. PA and DPM must not introduce independent copies of PAS core entity stores.
2. PAS remains source of truth for portfolio lifecycle and state lineage.
3. PA and DPM outputs are derived/decision layers and should be versioned separately from PAS core records.

## Next Steps

1. Add BFF contract definitions for PAS-connected and direct-input modes.
2. Add canonical glossary mapping across PAS/PA/DPM DTOs.
3. Add API-level provenance fields (`source_system`, `as_of_date`, `correlation_id`) for cross-service auditability.
