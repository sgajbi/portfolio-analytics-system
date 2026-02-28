# Shared Requirement: Query, Audit, and Observability

## Query Contract

Each transaction RFC must define the minimum data visible to downstream consumers after processing, including:

- enriched transaction
- derived business state
- linkage state
- policy metadata
- audit metadata

## Audit Requirement

All derived outputs must be reproducible from:

- source data
- linked data
- active policy

## Observability Requirement

Each transaction RFC must define:

- required logs
- required metrics
- required status states
- minimum diagnostics for incident support

## Minimum Status States

- received
- validated
- enriched
- processed
- partially processed
- parked
- failed
- reconciled
