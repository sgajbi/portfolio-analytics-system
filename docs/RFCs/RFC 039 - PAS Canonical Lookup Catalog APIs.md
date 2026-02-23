# RFC 039 - PAS Canonical Lookup Catalog APIs

- Status: IMPLEMENTED
- Date: 2026-02-23
- Owners: PAS Query Service

## Context

UI and BFF require stable selector catalogs for portfolios, instruments, and currencies.
Previously, BFF had to derive these lookups from low-level PAS APIs, which duplicated mapping logic outside PAS.

## Decision

Add canonical PAS lookup endpoints in Query Service:

- `GET /lookups/portfolios`
- `GET /lookups/instruments?limit=...`
- `GET /lookups/currencies?instrument_page_limit=...`

Contract:

```json
{
  "items": [
    { "id": "...", "label": "..." }
  ]
}
```

Implementation notes:
- Portfolios: sourced from `PortfolioService.get_portfolios()` and mapped to `{id,label}` by `portfolio_id`.
- Instruments: sourced from `InstrumentService.get_instruments(skip=0, limit=limit)` and labeled as `"<security_id> | <name>"`.
- Currencies: derived as distinct uppercase codes from portfolio base currencies and all instrument currencies, with paged instrument retrieval.

## Rationale

- PAS remains the system of record for reference-data lookups.
- BFF/UI integration contracts become simpler and more consistent.
- Selector vocabulary is centralized and governed at backend level.

## Consequences

Positive:
- Reduced duplication in BFF and UI layers.
- Better domain boundary: lookup catalogs owned by PAS.

Trade-offs:
- Currency lookup currently derives from available reference data rather than a dedicated currency master.

## Follow-ups

- Add a PAS-managed currency master endpoint when master-data service is introduced.
- Add tenant/book-center scoped lookup filters when entitlement model is introduced.
