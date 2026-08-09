# Phase 1 live provider-evidence execution

The remaining Phase 1 provider uncertainty is primarily empirical. The repository therefore exposes one conservative, resumable entry point for the live campaigns:

```powershell
uv run python scripts/run_phase1_live_evidence.py --max-new-cases 10
```

Before provider calls, run the local preflight when useful:

```powershell
uv run python scripts/run_phase1_live_evidence.py --preflight
```

The main command advances evidence in this order:

1. Run or resume the representative EODHD campaign in bounded batches.
2. When the representative campaign is complete, aggregate and benchmark it through the existing EODHD workflow and register the storage evidence.
3. If `TIINGO_API_KEY` is configured, run or resume the bounded EODHD/Tiingo validation campaign.
4. Register the cross-provider report into the local Phase 1 runtime-evidence manifest.

The command requires `EODHD_API_TOKEN` or `EODHD_API_KEY`. Tiingo is not required to continue the primary campaign; if `TIINGO_API_KEY` is absent after the primary campaign completes, secondary validation remains explicitly outstanding.

Use the following command to inspect local progress without making provider calls:

```powershell
uv run python scripts/run_phase1_live_evidence.py --status-only
```

## Live correction-lookback evidence

After the representative aggregate exists, the EODHD deterministic daily-update criterion can be tested directly against that immutable parent dataset. Choose one active symbol contained in the representative campaign and a date window that overlaps the parent history, then run:

```powershell
uv run python scripts/run_eodhd_live_daily_update.py `
  --symbol AAPL.US `
  --start 2026-07-20 `
  --end 2026-08-09 `
  --target-version eodhd-live-update-2026-08-09-v1
```

The runner performs a real EODHD retrieval through the same canonical normalization path, matches the retrieved security to the immutable representative parent dataset, and assesses appended, revised, and unchanged overlapping observations. The report is marked as a live-provider observation. It is registered into the Phase 1 evidence manifest only when the run contains genuine overlap; append-only or otherwise non-demonstrating runs remain unregistered and return a non-zero status.

This bounded update test demonstrates correction-lookback mechanics for the observed security and interval. It does not by itself establish representative provider quality, corporate-action completeness, or licensing acceptance.

Completed provider work is checkpointed by the underlying campaign runners. Re-running the same command therefore advances remaining cases rather than repeating successful cases.

Runtime evidence registration does not modify or promote the checked-in acceptance ledgers. Phase 1 remains closed until the semantic review and both checked-in acceptance gates support completion.
