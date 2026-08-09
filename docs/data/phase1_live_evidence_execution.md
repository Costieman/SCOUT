# Phase 1 live provider-evidence execution

The remaining Phase 1 provider uncertainty is primarily empirical. The repository therefore exposes one conservative, resumable entry point for the live campaigns:

```powershell
uv run python scripts/run_phase1_live_evidence.py --max-new-cases 10
```

The command advances evidence in this order:

1. Run or resume the representative EODHD campaign in bounded batches.
2. When the representative campaign is complete, aggregate and benchmark it through the existing EODHD workflow and register the storage evidence.
3. If `TIINGO_API_KEY` is configured, run or resume the bounded EODHD/Tiingo validation campaign.
4. Register the cross-provider report into the local Phase 1 runtime-evidence manifest.

The command requires `EODHD_API_TOKEN` or `EODHD_API_KEY`. Tiingo is not required to continue the primary campaign; if `TIINGO_API_KEY` is absent after the primary campaign completes, secondary validation remains explicitly outstanding.

Use the following command to inspect local progress without making provider calls:

```powershell
uv run python scripts/run_phase1_live_evidence.py --status-only
```

Completed provider work is checkpointed by the underlying campaign runners. Re-running the same command therefore advances remaining cases rather than repeating successful cases.

Runtime evidence registration does not modify or promote the checked-in acceptance ledgers. Phase 1 remains closed until the semantic review and both checked-in acceptance gates support completion.
