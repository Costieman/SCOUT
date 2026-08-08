# Historical backfill orchestration

The backfill layer turns one explicit provider/date/symbol request into deterministic bounded batches and makes progress resumable without silently skipping work.

## Contract

`plan_daily_bar_backfill` sorts and validates the requested provider symbols, partitions the inclusive date interval into fixed calendar-day windows, partitions symbols into bounded chunks, and hashes the complete specification into a stable plan ID. Every batch receives a deterministic batch ID. Provider-specific rate limits are not embedded in this planner; the concrete provider transport owns pacing/retry policy.

`execute_daily_bar_backfill` runs only batches that are not already marked complete. Each request uses the normal provider-neutral `DailyBarRequest`. Returned records must match the expected provider, symbol set, and date window and must not contain duplicate provider-instrument/session observations.

## Resume and immutability

`BackfillRuntimeStore` writes provider-neutral staged batch records outside Git. A batch is marked complete only after its staged representation is durable. Repeating an identical persist is idempotent; attempting to reuse the same deterministic batch identity with different staged content fails explicitly.

The checkpoint is written atomically and records completed batch IDs in plan order. If a later batch fails, rerunning the same plan skips completed batches and resumes from the first unfinished batch. A fully loaded plan rejects missing batches and duplicate instrument/date observations across batches.

This staged representation is not a replacement for the raw zone. A concrete provider adapter must still preserve exact vendor response bytes through the raw-capture boundary whenever licensing permits. The staged backfill exists so normalization and quality checks can resume deterministically without pretending an incomplete run is a valid canonical dataset.

## Promotion boundary

Backfill completion does **not** imply research readiness. Staged records must still pass:

1. permanent instrument-identity resolution;
2. canonical normalization and adjustment-policy checks;
3. structural/contextual data-quality checks;
4. point-in-time universe construction;
5. required cross-provider reconciliation; and
6. immutable canonical dataset promotion with provenance/version metadata.

No partial backfill is promoted merely because some provider requests succeeded.
