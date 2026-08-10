# Trade Scout local research console v0.1

## Purpose

The local console is the first continuously viewable Trade Scout application surface. It is a
read-only presentation process over persisted application-service evidence. It does **not** call
Tiingo, Alpha Vantage, Stooq, Alpaca, or any brokerage API; it does not expose licensed raw market
data; and it contains no feature, pattern, event, risk, ranking, or trade-execution logic.

The console exists so Phase 1 data-foundation state is visible while the analytical system is still
being built. A blocked or unknown state is shown as such rather than being replaced with a plausible
number.

## Quick start

From the repository root:

```bash
uv sync --locked --dev
uv run python scripts/serve_trade_scout.py --open-browser
```

The default address is:

```text
http://127.0.0.1:8765/
```

The page refreshes every 15 seconds. Each refresh re-reads the configured persisted evidence, so
new campaign state or discrepancy reports appear without restarting the server.

The server binds only to loopback by default. Binding to a non-loopback interface requires the
explicit `--allow-remote` flag; this is intentionally inconvenient because this development server
has no authentication layer.

## Operational Data Health control plane

The Data Health workspace now exposes a concise operational control plane above the provider table.
It is derived only from persisted evidence supplied to the application service. The panel includes:

- explicit Phase 1 blockers rather than a generic red/green project flag;
- durable Tiingo acquisition progress when safe campaign state is supplied;
- the latest campaign status and observation time;
- cumulative quota-pause and failure counts;
- the most recent rate-limited or failed symbol when recorded by safe state;
- cross-provider review-work count, missing-session observations, and discrepancies;
- corporate-action anomaly and ingestion-failure counts when those artifacts are supplied.

A missing input remains `Unknown` and can itself produce a visible evidence-gap blocker. The console
does not infer a zero count from an absent report and does not query a provider to fill the gap.

## Evidence inputs

The default launch reads the checked-in Tiingo and free-provider acceptance assessments. Additional
runtime evidence can be supplied explicitly:

```bash
uv run python scripts/serve_trade_scout.py \
  --tiingo-safe-state /private/trade-scout/safe-state.json \
  --composite-evidence /private/trade-scout/composite-evidence.json \
  --canonical-root /private/trade-scout/canonical-store \
  --canonical-dataset-version DATASET_VERSION \
  --scanner-required-session 2026-08-07 \
  --open-browser
```

`--tiingo-safe-state` is metadata-only campaign state. Raw Tiingo response directories are neither
served nor traversed by the console. Canonical storage is accessed only through the existing
canonical manifest/store boundary.

## Routes

- `/` and `/index.html` — HTML research console.
- `/api/data-health.json` — provider-independent Data Health contract, including blockers and
  provider operational metadata.
- `/api/snapshot.json` — complete presentation-ready application snapshot.
- `/healthz` — local process/application-gate status, including blocker and review counts. This is
  not a live provider-connectivity test.

All responses are `no-store` and include restrictive browser security headers. Normal POST requests
are rejected; the console has no mutation or order-entry routes.

## Phase 1 gating

At this stage the expected default state is:

- Data Health: visible and evidence-backed.
- Research Lab: preview only.
- Scanner: blocked until an accepted fresh canonical dataset and production-eligible strategy exist.
- Alerts: blocked.
- Trade execution: absent by design.

The frontend remains replaceable. The stable asset is the typed application/API contract and the
read-only application services underneath it, not this particular stdlib HTTP implementation.
