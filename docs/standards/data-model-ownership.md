# Data Model Ownership

- Service: `lotus-core`
- Ownership: canonical core portfolio data model and persistence.

## Owned Domains

- Portfolios and portfolio reference metadata.
- Transactions, positions, valuations, cost basis, PnL, and timeseries.
- Market and instrument reference links needed for core processing.

## Service Boundaries

- lotus-core exposes standardized core data APIs.
- lotus-performance consumes lotus-core APIs for advanced analytics.
- lotus-report consumes lotus-core and lotus-performance APIs for reporting aggregation.

## Schema Rules

- Entity names follow canonical glossary vocabulary.
- Ownership stays within lotus-core database boundary; no cross-service shared DB.

