# Shared Requirement: Normative Rules and Precedence

## Interpretation Rules

- `must` means mandatory behavior
- `must not` means prohibited behavior
- `may` means optional behavior
- `default` means the standard behavior when no explicit customer policy overrides it

## Precedence Order

If requirements conflict, resolve in this order:

1. transaction-specific formula definitions
2. transaction-specific explicit rules
3. active configuration policy
4. shared common rules
5. examples and illustrations

## Validation Precedence

- explicit validation rules override permissive upstream input
- missing policy-required data must fail or park processing
- silently inferring business-critical values is prohibited when explicit input or policy is required

## Conflict Rule

If two active policies conflict, processing must fail as a policy-resolution error unless a higher-order policy explicitly defines tie-breaking behavior.
