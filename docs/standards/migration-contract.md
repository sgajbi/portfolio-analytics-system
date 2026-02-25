# Migration Contract Standard

- Service: `portfolio-analytics-system`
- Persistence mode: Alembic-managed relational schema.
- Migration policy: versioned, deterministic, forward-only in production.

## Deterministic Checks

- `make migration-smoke` validates migration inventory and executes:
  - `python -m alembic heads`
  - `python -m alembic upgrade head --sql`
- CI executes `make migration-smoke` on each PR.

## Apply Command

- `make migration-apply` executes `alembic upgrade head`.

## Rollback and Forward-Fix

- Production rollback is forward-fix oriented; never edit applied migration files.
- If migration issues are found, publish a new corrective migration revision.
