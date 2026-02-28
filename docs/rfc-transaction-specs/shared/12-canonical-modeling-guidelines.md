# Shared Requirement: Canonical Modeling Guidelines

## Purpose

Define shared modeling rules for transaction RFCs and implementation models.

## Composition Rule

Every transaction RFC must define one top-level transaction model composed from smaller reusable sub-models.

## Required Field Metadata

Each field in the physical field catalog must define:

- field name
- type
- required or optional
- default
- sample value
- description
- validation rule
- source classification
- mutability classification

## Reuse Rule

Common sub-models should be reused across transaction types where semantics are shared, while transaction-specific extensions remain in the transaction RFC.

## Examples of Reusable Sub-Models

- transaction identity
- lifecycle
- instrument reference
- fx details
- classification details
- linkage details
- audit metadata
- policy metadata
