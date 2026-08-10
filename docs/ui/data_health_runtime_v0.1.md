# Data Health runtime v0.1

The Phase 1 interface is intentionally split into a read-only application service and a
replaceable renderer. The Data Health service reads persisted evidence; it never calls market-data
providers and never computes features, patterns, rankings, or research results.

## Evidence inputs

The renderer can consume:

- the checked-in Tiingo provider assessment;
- the checked-in free-stack assessment for Alpha Vantage and Stooq;
- an optional persisted Tiingo safe campaign state;
- zero or more A+B composite-evidence JSON reports;
- an explicitly selected canonical storage root and dataset version;
- an explicit scanner-required session date;
- optional ingestion-failure markers and corporate-action anomaly reports.

If an evidence source is not supplied, the corresponding anomaly count is `None` rather than an
invented zero. If no canonical dataset version is explicitly selected and registered, Data Health
is `BLOCKED` and Scanner freshness is `BLOCKED`.

## Render a current Phase 1 snapshot

```bash
uv run python scripts/render_trade_scout_data_health.py \
  --output runtime/ui-data-health/index.html
```

That command uses only checked-in provider assessments. It will therefore show the current
pre-canonical state and will not claim live campaign progress that is not present locally.

When durable campaign state and validation reports exist, pass them explicitly:

```bash
uv run python scripts/render_trade_scout_data_health.py \
  --tiingo-safe-state /durable/trade-scout/safe-state.json \
  --composite-evidence /durable/trade-scout/reports/composite-evidence.json \
  --canonical-root /durable/trade-scout/canonical-store \
  --canonical-dataset-version DATASET_VERSION \
  --scanner-required-session YYYY-MM-DD \
  --output runtime/ui-data-health/index.html
```

The generated HTML is a local diagnostic client, not a deployed website. A later frontend may
replace it without changing the typed dashboard contracts or the application service.
