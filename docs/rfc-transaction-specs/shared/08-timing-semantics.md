# Shared Requirement: Timing Semantics

## Purpose

Define the shared timing model for all transaction RFCs.

## Timing Dimensions

Each transaction RFC must define behavior for:

- economic timing
- position timing
- cash timing
- performance timing
- reporting timing

## Supported Timing Values

- `TRADE_DATE`
- `SETTLEMENT_DATE`

## Rule

A transaction RFC must explicitly state:

- when exposure becomes effective
- when quantity becomes settled
- when cash is reserved
- when cash is settled
- how read-models differ by timing mode

## Transition Requirement

If a transaction can exist in unsettled state, the RFC must define the transition from unsettled to settled state.
