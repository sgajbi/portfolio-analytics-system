# RFC --- Portfolio Analytics: Robust, Resilient & Scalable Valuation Pipeline

**Status:** Draft 1\
**Date:** 26 Aug 2025\
**Owner:** `<you>`{=html}

## Executive Summary

The valuation pipeline is generating jobs for dates before positions
exist, causing `DataNotFoundError`, DLQ pollution, and consumer
shutdowns.\
This RFC proposes position-aware scheduling, better error taxonomy,
durable job lifecycle states, negative caching, and improved
observability.

## Problem

1.  Scheduler creates jobs before first-open date of a position.\
2.  `DataNotFoundError` treated as retryable, leading to retries, DLQ
    entries, and shutdowns.\
3.  No durable lifecycle state; invalid jobs keep reappearing.\
4.  Operational noise and unstable throughput.

## Goals

-   No jobs before first-open date.\
-   Non-retry for permanent gaps; retry only transient errors.\
-   Exactly-once side effects.\
-   Strong observability, metrics, alerts.\
-   Horizontal scalability.

## Proposed Changes

### Scheduler

-   Compute `first_open_date` per `(portfolio, security, epoch)`.\
-   Start jobs at `max(watermark+1, first_open_date−1)`.\
-   If no open date, mark key `NO_POSITION`.

### Consumer

-   Retryable: DB, missing price/FX.\
-   Non-retryable: `DataNotFoundError` → mark `SKIPPED_NO_POSITION`, no
    DLQ.

### Job Lifecycle

-   `status`: {PENDING, CLAIMED, COMPLETE, RETRYABLE_FAILED,
    SKIPPED_NO_POSITION}.\
-   `failure_reason`, `attempt_count`.\
-   Negative caching: don't recreate skipped jobs unless earlier data
    appears.

### Observability

-   Prometheus metrics: jobs created, skipped, retries, DLQ.\
-   Alerts on DLQ \>0.5% and skip anomalies.\
-   OpenTelemetry spans for tracing.

### Health

-   Consumers never exit on data gaps.\
-   Circuit breaker for noisy keys.

## Schema

``` sql
ALTER TABLE valuation_jobs
  ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING',
  ADD COLUMN failure_reason TEXT NULL,
  ADD COLUMN attempt_count INT NOT NULL DEFAULT 0;
```

## Test Plan

-   Unit: scheduler start date, consumer error handling.\
-   Integration: ensure no jobs before positions.\
-   Load: simulate millions of jobs, confirm bounded retries.

## Rollout

1.  DB migration.\
2.  Release consumer error handling.\
3.  Release scheduler with position-aware backfill.\
4.  Enable negative caching.\
5.  Turn on alerts.

Rollback: feature flags.

## Risks

-   Slow queries → add indexes, cache first_open_date.\
-   Late data → trigger re-eval.\
-   Schema drift → migration checks.

## Acceptance Criteria

-   No jobs created before first-open date.\
-   `DataNotFoundError` skipped, not retried or DLQ.\
-   Consumers remain alive.\
-   DLQ rate \<0.5% (transient only).\
-   Deterministic backfills complete within SLOs.
