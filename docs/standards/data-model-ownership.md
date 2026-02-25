# Data Model Ownership

- Service: `portfolio-analytics-system`
- Ownership: canonical core portfolio data model and persistence.

## Owned Domains

- Portfolios and portfolio reference metadata.
- Transactions, positions, valuations, cost basis, PnL, and timeseries.
- Market and instrument reference links needed for core processing.

## Service Boundaries

- PAS exposes standardized core data APIs.
- PA consumes PAS APIs for advanced analytics.
- RAS consumes PAS and PA APIs for reporting aggregation.

## Schema Rules

- Entity names follow canonical glossary vocabulary.
- Ownership stays within PAS database boundary; no cross-service shared DB.
