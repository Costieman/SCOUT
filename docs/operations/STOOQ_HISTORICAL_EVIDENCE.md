# Stooq historical OHLCV evidence

The free-data-first Phase 1 path treats Stooq as a candidate historical daily-OHLCV source, not as an accepted canonical provider. This workflow collects bounded live evidence through the provider-neutral historical-evidence checks while preserving exact source responses outside Git.

Run one or more explicit cases with:

```bash
uv run python scripts/run_stooq_historical_evidence.py \
  --case AAPL.US,evidence:aapl-us,2000-01-03,2026-08-07,6000 \
  --case MSFT.US,evidence:msft-us,2000-01-03,2026-08-07,6000
```

Each case is retrieved twice. The evidence layer checks normalized repeatability, provider and symbol scope, date scope, duplicate instrument/session observations, deterministic order, minimum observation count, and configured start/end coverage. Runtime state is checkpointed so completed cases are not repeated after a later provider failure.

The `LINK_ID` is an explicit evidence identity supplied by the operator. It is not inferred from ticker text and is not, by itself, a canonical Trade Scout instrument identity. Cross-source identity reconciliation remains a separate acceptance gate.

Exact downloaded CSV bytes and raw manifests are stored beneath `runtime/stooq-historical-evidence/raw/`. JSON, Markdown, and checkpoint reports are stored beneath the sibling `report/` directory. Runtime data remain outside Git.

A passing campaign supports only the configured historical-retrieval and repeatability claim. It does not establish Stooq adjustment semantics, inactive/delisted coverage, licensing or redistribution rights, correction behavior over longer intervals, representative-universe suitability, or canonical-provider acceptance. Those claims require separate evidence.
