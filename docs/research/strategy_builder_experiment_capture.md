# Strategy Builder experiment capture

## Purpose

Interactive Strategy Builder research must become part of the same durable experiment record used by governed research rather than disappearing when a browser tab closes. This integration deliberately reuses the existing `ExperimentRunner`, `FileManifestStore`, `IndexedManifestStore`, and `DuckDBExperimentRegistry`; it does not create a second experiment database or a second analytical engine.

## Runtime layout

When `scripts/serve_research_workbench.py` starts against a private operator workspace, Strategy Builder experiment state is written beneath:

```text
<workspace>/research/experiments/
  registry.duckdb
  exp_<id>/
    manifest.json
    artifacts/
      strategy_builder.json
      # or strategy_builder_entry_sweep.json
```

The JSON manifest is authoritative. `registry.duckdb` is a queryable metadata index used for discovery and lineage. The index may be rebuilt from verified manifests; it is not analytical truth.

## What is captured

Every successful normal Strategy Builder run records:

- immutable experiment ID and EXPLORATORY mode;
- selected canonical dataset and reviewed-universe identity;
- exact source-code commit;
- complete resolved entry definition, ranking/selection settings, holding horizon, exit candidates, and execution-cost assumptions;
- explicit `point_in_time_membership_claimed = false` for the current reviewed canonical cohort;
- entry-event and complete-event counts;
- event-population fingerprint;
- complete exit-policy summary metrics and runtime timings;
- warnings and artifact checksums.

Entry-parameter sweeps additionally record the target feature, parameter, full declared value range, value count, search-space fingerprint, and every response-surface point. The parent experiment stores the complete sweep. Converting individual sweep cells into separately scheduled child experiments belongs to the later asynchronous/batch-execution milestone rather than being faked by this synchronous UI adapter.

## Failure behavior

The analytical service runs inside `ExperimentRunner`. If the service fails, the runner first writes a terminal `FAILED` manifest and updates the DuckDB index, then the browser receives an error that includes the saved experiment ID. Failed research therefore remains visible to the future Experiment Library and research-brain layer.

## UI behavior

A successful Strategy Builder result includes a **Saved experiment record** card showing the experiment ID, status, research mode, dataset version, and manifest checksum. The browser page is presentation; the manifest and structured stage artifact are the durable research record.

## Research-brain boundary

This change is intentionally the storage foundation, not the research-brain implementation. A future brain should reference immutable experiment IDs and add higher-level mission, notes, evidence synthesis, open questions, and cross-brain exchange without rewriting or deleting the underlying experiment history. Negative, null, failed, and successful experiments remain available to that layer.

## Current exclusions

This first capture slice does not yet provide:

- automatic PDF generation;
- an Experiment Library page;
- research-brain membership or synthesis;
- asynchronous background sweeps, progress bars, resume, or cancellation;
- automatic experiment suggestions;
- confirmatory promotion or validation claims.

Those features can now be built on a durable evidence substrate instead of browser-local history.
