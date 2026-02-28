# Shared Requirement: Test Strategy and Gap Assessment

## Mandatory Test Categories

Each transaction RFC must define tests for:

- validation
- calculation
- state changes
- timing
- linkage
- query visibility
- idempotency and replay
- failure modes
- observability where applicable

## Characterization Rule

If existing behavior already matches the RFC, that behavior must be protected by characterization tests before refactoring.

## Gap Assessment Template

For each requirement, implementation review must capture:

- requirement id or title
- implementation status: covered / partially covered / not covered
- behavior match: matches / partially matches / does not match
- current observed behavior
- target required behavior
- proposed action
- risk if unchanged
- blocking or non-blocking
