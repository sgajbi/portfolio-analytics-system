# BUY Slice 1 Validation Reason Codes

This document defines the initial BUY validation reason-code catalog introduced in Slice 1.

| Code | Field | Meaning |
|---|---|---|
| `BUY_001_INVALID_TRANSACTION_TYPE` | `transaction_type` | Payload is not BUY while being validated under BUY canonical rules. |
| `BUY_002_MISSING_SETTLEMENT_DATE` | `settlement_date` | Settlement date is mandatory for canonical BUY validation. |
| `BUY_003_NON_POSITIVE_QUANTITY` | `quantity` | BUY quantity must be strictly greater than zero. |
| `BUY_004_NON_POSITIVE_GROSS_AMOUNT` | `gross_transaction_amount` | Gross amount must be strictly greater than zero. |
| `BUY_005_MISSING_TRADE_CURRENCY` | `trade_currency` | Trade currency is required. |
| `BUY_006_MISSING_BOOK_CURRENCY` | `currency` | Booked currency is required. |
| `BUY_007_INVALID_DATE_ORDER` | `transaction_date` | Trade date must not be after settlement date. |
| `BUY_008_MISSING_LINKAGE_IDENTIFIER` | `economic_event_id` | Strict mode requires linkage identifiers. |
| `BUY_009_MISSING_POLICY_METADATA` | `calculation_policy_id` | Strict mode requires policy id and version. |

## Notes

- Slice 1 introduces this catalog and validator foundation.
- Runtime strict enforcement in live ingestion flow is staged for later slices.
- Strict mode is currently available through domain validator invocation (`strict_metadata=True`).

