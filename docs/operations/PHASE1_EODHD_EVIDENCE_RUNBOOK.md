# Phase 1 EODHD Evidence Runbook

This runbook is the operational handoff for the representative EODHD evidence campaign. It does not weaken or bypass the Phase 1 acceptance gates.

## Preconditions

From the repository root, use the locked environment and ensure either `EODHD_API_TOKEN` or `EODHD_API_KEY` is loaded into the current shell. Runtime outputs remain under `runtime/` and are intentionally excluded from Git.

## Normal execution

Run:

```powershell
uv run python scripts/run_phase1_eodhd_evidence.py --max-new-cases 10
```

The command is deliberately resumable. On the first invocation it freezes the representative plan if one does not already exist, then executes at most the requested number of new cases. Completed cases are checkpointed. Re-running the identical command continues from the next pending case rather than repeating successful provider work.

To inspect progress without making provider calls:

```powershell
uv run python scripts/run_phase1_eodhd_evidence.py --status-only
```

## Automatic completion path

When the representative campaign becomes complete, the same launcher automatically:

1. verifies and aggregates the per-case canonical datasets into the representative aggregate dataset;
2. applies the checked-in representative-storage policy;
3. runs the Parquet/DuckDB benchmark only if that scope gate passes; and
4. registers the resulting storage-evidence report by exact SHA-256 checksum in the local Phase 1 evidence manifest.

Registration is evidence bookkeeping only. It does not modify either checked-in acceptance ledger and cannot promote Phase 1 by itself.

## Failure behavior

Provider failures remain visible. The campaign checkpoint is retained, so a later identical invocation resumes completed work. Missing credentials, malformed plans, contradictory evidence, failed representativeness, or invalid runtime manifests fail closed rather than being converted into successful acceptance evidence.

## Expected operational cadence

Use bounded batches appropriate to the provider account and current rate limits. A batch size is a provider-call budget, not an acceptance threshold. Changing the batch size does not change the frozen campaign sample or the scientific acceptance criteria.
