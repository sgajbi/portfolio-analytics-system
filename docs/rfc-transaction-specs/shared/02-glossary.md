# Shared Requirement: Glossary

## Purpose

Define common terms used across all transaction RFCs.

## Required Common Terms

Each transaction RFC must use these shared meanings unless explicitly overridden:

- trade date: date of execution
- settlement date: contractual legal settlement date
- booking date: accounting booking date
- value date: ledger value date
- gross principal: principal amount before fees and accrued interest
- book cost: amount added to cost basis under policy
- dirty settlement amount: total settlement cash amount
- held-since date: start of current continuous holding period
- economic event: one business event represented by one or more linked records
- linked transaction group: grouping id for all records in the same economic event
- cashflow classification: analytical cash meaning
- income classification: income meaning
- realized capital pnl: realized price-driven pnl excluding fx
- realized fx pnl: realized exchange-rate-driven pnl
- calculation policy: versioned configuration used during processing

## Rule

If a transaction RFC uses a term defined here, it must use the shared definition unless the RFC explicitly documents a transaction-specific override.
