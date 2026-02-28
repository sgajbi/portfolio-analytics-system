# Shared Requirement: Common Processing Lifecycle

## Purpose

Define the common lifecycle stages that every transaction type must follow.

## Canonical Lifecycle

Every transaction must be processed in this order:

1. receive and ingest
2. validate
3. normalize and enrich
4. resolve policy
5. calculate
6. create business effects
7. persist and publish
8. expose read-model visibility
9. emit observability and support signals

## Rule

A transaction RFC may add transaction-specific logic inside a lifecycle stage, but it must not remove or reorder the lifecycle stages unless explicitly approved at platform level.

## Minimum Supportability Requirement

Every lifecycle stage must be diagnosable via status, logs, or persisted state.
