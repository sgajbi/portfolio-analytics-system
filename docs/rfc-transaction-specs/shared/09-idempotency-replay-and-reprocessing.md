# Shared Requirement: Idempotency, Replay, and Reprocessing

## Purpose

Define safe processing behavior for repeated, replayed, or rebuilt transactions.

## Required Concepts

Every transaction RFC must define:

- idempotency key
- replay behavior
- duplicate detection behavior
- reprocessing behavior
- conflict behavior for same business event with inconsistent payload

## Rule

Reprocessing the same transaction under the same policy and same input must be deterministic.

## Conflict Handling

If the same transaction id or same economic event arrives with materially different payload, the RFC must define whether to:

- reject
- park
- replace under approved correction flow
- escalate as reconciliation conflict
