# Shared Requirement: Accounting, Cash, and Linkage

## Purpose

Define the common framework for security-side and cash-side effects.

## Dual-Accounting Requirement

Each transaction RFC must specify whether it:

- creates only an analytical cashflow
- creates a linked cash ledger entry
- supports both engine-generated and upstream-provided cash entries

## Required Linkage Model

Where a transaction and cash entry are linked, the model must support:

- economic event id
- linked transaction group id
- originating transaction id
- linked cash transaction id
- link type
- reconciliation key where applicable

## Cash Views

Each transaction RFC must define the impact on:

- available cash
- settled cash
- projected cash
- ledger cash

## Rule

No cash-side effect may exist without explicit linkage or an explicitly documented external expectation.
