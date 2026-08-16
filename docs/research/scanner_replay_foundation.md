# Historical Scanner Replay Foundation v0.1

## Purpose

This slice establishes the first scanner execution path without enabling live production scanning. It implements the `REPLAY` mode required by the Scanner & Ranking specification so the production-shaped pathway can be challenged on historical sessions before a production scanner exists.

The governing rule is unchanged: **the scanner may apply research; it may not invent research**.

## Production eligibility boundary

A normal production-compatible replay requires an explicit `PRODUCTION-ELIGIBLE` research decision whose subject is the exact strategy version being replayed. Candidate, validated, exploratory, or undecided definitions are rejected from that path.

A non-production strategy may be replayed only with the explicit research-preview switch. The resulting manifest and every emitted candidate are labelled `RESEARCH_PREVIEW`. This does not promote the strategy and cannot be represented as an ordinary production-compatible replay.

No `END_OF_DAY` or `INTRADAY` execution function is introduced in this slice.

## Point-in-time replay rule

`run_historical_replay()` receives an as-of session, a point-in-time eligible universe, point-in-time ticker displays, and bar histories. Before the shared analytical evaluator is called, each history is truncated to rows whose trade date is at or before the replay date.

This has two important consequences:

1. Later rows may exist in storage but are not observable by the replayed analytical path.
2. Adding a future suffix must not change the scan-run identity, output checksum, candidate state, pattern identity, or event identity for an earlier replay date.

The replay also requires the exact strategy dataset version. It does not substitute another dataset or provider snapshot.

## Shared research logic

The first concrete adapter is `ConsolidationReplayEvaluator`. It invokes the existing `replay_consolidation_pipeline()` used by historical Pattern/Event research. It does not copy consolidation, lifecycle, breakout, volume-confirmation, or cooldown logic into the scanner package.

The adapter projects canonical states into the scanner contract:

- `QUALIFIED` -> `QUALIFIED`
- `TRIGGER_READY` -> `TRIGGER_READY`
- same-session registered breakout event -> `TRIGGERED`
- `INVALIDATED` -> `INVALIDATED`

The existing consolidation pipeline does not currently emit standalone `FORMING` or `COOLDOWN` snapshots. This foundation therefore does not fabricate them. Those scanner states remain in the stable contract for later upstream support.

## Candidate and run provenance

A `ScanCandidate` retains:

- scan-run identity and as-of date;
- permanent instrument identity and point-in-time ticker display;
- strategy family and immutable strategy version;
- pattern instance and optional event identity;
- current state, current-value snapshot, and structural levels;
- evidence profile identity and evidence-package checksum;
- optional risk-policy identity;
- ranking-model identity when one is eventually attached;
- data freshness, quality status, dataset version, and replay publication class.

The replay manifest additionally retains the exact universe version, feature-set version, software/code version, configuration-schema version, eligible instrument list, per-instrument execution records, candidate counts by state, warnings, and an output checksum.

Execution duration is represented in the manifest contract but intentionally remains unset in this deterministic foundation. Performance benchmarking belongs to a later operational acceptance step.

## Visible failure

Replay distinguishes an evaluated instrument with no candidate from an instrument that could not be evaluated normally. Explicit blocked states cover:

- no point-in-time history;
- no bar for the requested as-of session;
- missing point-in-time ticker display;
- failed eligibility or data quality on the replay session;
- dataset-version mismatch.

Blocked instruments are retained in the run manifest and generate warnings. They are never silently converted into "no setup".

## Ranking boundary

This slice deliberately emits no composite rank. `rank_score` and rank components remain empty. The Scanner & Ranking specification recommends transparent evidence presentation before composite ranking is promoted, and ranking itself requires independent out-of-sample validation.

The replay foundation therefore establishes the scanner state/provenance path first. Ranking research remains downstream work.

## Synthetic acceptance

Synthetic integration tests verify that the scanner projection on the known consolidation-breakout session produces the same event ID and pattern instance as the canonical Pattern/Event replay. A second test proves that adding future bars cannot rewrite the earlier scanner replay output.

## Deliberate exclusions

This slice does not implement:

- live end-of-day scanning;
- data-age/freshness scheduling policy;
- a production strategy registry;
- scanner persistence/storage;
- composite ranking or rank validation;
- evidence cohort selection logic;
- alert generation or suppression;
- UI publication;
- trading or portfolio allocation.

Those boundaries are intentional. Historical replay is the acceptance foundation on which production scanner behavior can later depend.
