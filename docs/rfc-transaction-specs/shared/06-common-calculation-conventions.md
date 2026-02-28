# Shared Requirement: Common Calculation Conventions

## Purpose

Define shared calculation rules that apply across transaction types.

## Numeric Rules

- all business-critical numeric values must use decimal-safe arithmetic
- floating-point arithmetic must not be used for financial calculations
- precision and rounding must be policy-driven and documented

## Base and Local Currency

Each transaction RFC must define:

- local amount fields
- base amount fields
- fx source
- fx precision and rounding

## Required Explicitness

If a transaction produces realized pnl, the transaction RFC must define both:

- realized capital pnl
- realized fx pnl

If a transaction does not realize pnl, the RFC must define whether those fields are explicit zero values or not applicable.

## Formula Rule

Every transaction RFC must define:

- input values
- derived values
- formula order
- default formulas
- policy-driven variants
