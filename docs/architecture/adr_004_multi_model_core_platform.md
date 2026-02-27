# ADR 004 - lotus-core Multi-Model Core Platform Direction

## Status
Accepted

## Context
lotus-core must remain the canonical core platform for the Lotus ecosystem while supporting multiple interaction patterns required by platform consumers and operations.

## Decision
lotus-core will evolve as a multi-model core platform with the following principles.

1. Core interaction models
- File-based ingestion and bulk upload for large onboarding and batch processing.
- REST APIs for synchronous operational access.
- Kafka event integration for asynchronous streaming and service decoupling.

2. Core responsibilities
- Authoritative source of portfolio and financial core data for Lotus services.
- Deterministic transformation of transactions into positions.
- Core financial processing owned by lotus-core:
  - Cost basis
  - Realized and unrealized P&L
  - Cashflow processing
  - Income calculations

3. Time series and aggregation
- Manage lifecycle for generated time series.
- Provide position-level and portfolio-level rollups.
- Produce aggregated datasets for downstream analytics/reporting services.

4. Simulation support
- Provide simulation workflows for hypothetical trades.
- Produce before-and-after portfolio states without mutating canonical ledgers.
- Support integration for advisory and downstream analytics consumers.

5. Consistency and standardization
- Endpoints and contracts follow Lotus naming and vocabulary standards.
- Shared domain definitions and compatible API semantics are required.
- Inputs/outputs remain aligned with lotus-platform standards.

## Consequences
- lotus-core remains focused on core data and deterministic accounting capabilities.
- Advanced analytics and reporting services consume canonical outputs instead of duplicating core models.
- Contract drift is reduced through shared vocabulary and platform governance.
