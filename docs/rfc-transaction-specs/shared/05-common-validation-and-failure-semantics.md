# Shared Requirement: Common Validation and Failure Semantics

## Validation Categories

Every transaction type must define validation across:

- required fields
- numeric ranges and signs
- enum values
- referential integrity
- reconciliation tolerance
- linkage integrity
- policy-required fields

## Standard Failure Outcomes

Each validation or processing failure must resolve to one of:

- `HARD_REJECT`
- `PARK_PENDING_REMEDIATION`
- `ACCEPT_WITH_WARNING`
- `RETRYABLE_FAILURE`
- `TERMINAL_FAILURE`

## Rule

A transaction RFC must define which failures are mapped to which outcome.

## Support Requirement

All failures must produce:

- failure code
- failure reason
- lifecycle stage
- correlation id
- economic event id where available
