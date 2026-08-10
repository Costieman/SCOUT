# Phase 2 initial feature slice v0.1

## Purpose

This is the first provider-independent Feature Engine materialization over an immutable canonical
Trade Scout daily-bar dataset. It was first proven on the reviewed three-instrument canonical slice
and now remains reusable as the same mathematical feature set is applied to later immutable reviewed
dataset versions.

The feature layer never reads Tiingo raw files, Tiingo receipts, query tickers, or vendor-native
schemas. Its input is the canonical `DailyBar` contract and its provenance is the immutable canonical
dataset version/checksum.

## Initial registered feature set

Feature-set version: `phase2-initial-features-v0.1`.

| Feature | Definition | Price basis | Warm-up |
| --- | --- | --- | --- |
| `sma_50` | arithmetic mean of trailing 50 closes including t | split-adjusted | 50 observations |
| `sma_200` | arithmetic mean of trailing 200 closes including t | split-adjusted | 200 observations |
| `return_60` | close(t) / close(t-60 sessions) - 1 | split-adjusted | 61 observations |
| `avg_dollar_volume_20` | mean(raw close x raw reported volume) | raw | 20 observations |
| `rolling_range_pct_30` | (max adjusted high - min adjusted low) / current adjusted close x 100 | split-adjusted | 30 observations |

The raw basis for dollar volume is intentional: the measurement describes actual historical notional
traded on each session. Technical continuity measurements use split-adjusted price geometry.

ATR is deliberately not included in this first slice. The Feature Engine specification requires the
ATR smoothing convention to be explicitly finalized and versioned; that decision should be made in a
focused follow-up rather than smuggled into this foundational feature definition.

## Point-in-time behavior

Every calculation uses a trailing window ending at the current session. No centered windows or future
observations are permitted. A regression test changes future bars and verifies that earlier feature
values remain unchanged.

Warm-up is explicit. A fixed-window feature returns `WARMUP` until its declared minimum observation
count exists; it never silently shortens its window. Missing required split-adjusted inputs return
`INPUT_UNAVAILABLE` rather than substituting raw prices.

This feature set also requires every source canonical bar to carry `PASS` quality. A non-PASS input
fails the build rather than allowing the Feature Engine to reinterpret an upstream quality decision.

## Batch and incremental equivalence

`compute_incremental_initial_feature_frame` is intentionally correctness-first. It recomputes the
bounded history plus new sessions and returns only the new-session feature observations. This is not
yet the optimized production path; it is the reference behavior that future incremental caching or
columnar optimization must reproduce.

Tests compare incremental output with filtering a full batch computation over the same final dataset.

## Immutable derived storage

`FeatureSnapshotStore` writes a versioned private Parquet snapshot under:

```text
<workspace>/canonical-store/derived/features/
  <canonical-dataset-version>/<feature-set-version>/features.parquet
```

The feature manifest records:

- canonical dataset version;
- canonical logical content checksum;
- feature-set version;
- feature-definition checksum;
- record and availability counts;
- date range;
- logical feature content checksum; and
- physical Parquet checksum.

Reusing the same dataset/feature-set identity with different content or provenance fails. An identical
re-run is idempotent and reloads the existing immutable snapshot.

## Local run

The command accepts an explicit immutable canonical dataset version. To reproduce the original
three-instrument feature snapshot, run:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.1
```

After the reviewed identity expansion, the command defaults to
`tiingo-reviewed-split-only-v0.2`, so the shorter form builds the expanded feature snapshot:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private"
```

The command makes no provider calls. Metadata-only reports are versioned by both source dataset and
feature set, for example:

```text
<workspace>/evidence/feature-foundation/
  tiingo-reviewed-split-only-v0.1__phase2-initial-features-v0.1.json
  tiingo-reviewed-split-only-v0.2__phase2-initial-features-v0.1.json
```

The terminal/report output contains counts and checksums, not feature values or licensed price data.

## Scope boundary

A successful run proves that the Feature Engine can consume a named canonical dataset
deterministically. It does not mean the full Phase 1 data foundation is accepted, does not make a
small reviewed slice suitable for broad strategy conclusions, and does not make the Pattern Engine
production-ready. Dataset scope remains explicit in every derived snapshot.
