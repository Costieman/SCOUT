# Reviewed Tiingo canonical price promotion v0.1

## Purpose

This gate promotes only the bounded, reviewed Tiingo identity seed scope into immutable canonical
daily-bar storage. It is the first end-to-end proof that verified private provider history can become a
versioned Trade Scout price dataset without bypassing identity, adjustment, quality, or provenance
controls.

This promotion is deliberately **not** Tiingo provider acceptance and is **not** a production-serving
selection. The current scope remains the explicitly reviewed identity candidate only.

## Preconditions

The command requires:

1. a consistent private operator workspace;
2. checksum-verifiable Tiingo raw receipts for every reviewed query symbol;
3. `evidence/instrument-identity/tiingo-reviewed-candidate.json` with zero identity coverage gaps;
4. the matching immutable instrument-master snapshot already registered in `canonical-store`; and
5. split-only transformation and canonical normalization that produce only `PASS` rows.

Any missing receipt, checksum failure, identity mismatch, dated-symbol gap, quality issue, or eligible
Tiingo adjusted-price cross-check mismatch blocks promotion.

## Price semantics

Canonical rows preserve raw Tiingo OHLCV exactly through the normal provider normalization path.
Trade Scout split-adjusted OHLC is constructed from raw OHLC plus Tiingo event-date `splitFactor`:

```text
split_only_multiplier(d) = 1 / product(splitFactor(e) for split ex-dates e > d)
split_adjusted_OHLC(d) = raw_OHLC(d) * split_only_multiplier(d)
```

`divCash` is retained separately and never enters the split-only multiplier. Tiingo `adjOpen`,
`adjHigh`, `adjLow`, and `adjClose` are never used as canonical split-only prices because Tiingo's
adjusted series may include dividends. On a reviewed series with no dividend events, those fields may
be used only as a validation cross-check; disagreement blocks the promotion.

## Immutable output

The first bounded dataset identity is:

```text
dataset_id: equities_daily_reviewed_tiingo_slice
dataset_version: tiingo-reviewed-split-only-v0.1
```

The canonical Parquet file is registered by `CanonicalDailyBarStore` under:

```text
<workspace>/canonical-store/canonical/equities_daily/tiingo-reviewed-split-only-v0.1/daily_bars.parquet
```

The DuckDB dataset registry records source batch IDs, transformation version, adjustment-policy
version, reviewed identity snapshot version, quality-check version, logical content checksum, physical
Parquet checksum, record count, date range, and quality-state counts.

A metadata-only promotion report is written to:

```text
<workspace>/evidence/canonical-promotion/tiingo-reviewed-split-only-v0.1.json
```

The report contains no raw or adjusted OHLCV values.

## Run

From the repository root:

```powershell
uv run python .\scripts\promote_tiingo_reviewed_prices.py --root "$HOME\trade-scout-private"
```

The command is idempotent. A second run rebuilds the same reviewed slice, re-verifies source evidence,
and returns the existing immutable registration only if content and provenance still match.

## Scope boundary

A successful result proves the canonical storage pathway for the reviewed seed set. It does **not**:

- accept Tiingo as the project-wide primary provider;
- select this bounded dataset as the workspace serving dataset;
- prove exchange-session completeness for the broader campaign;
- establish point-in-time universe history for all acquired names;
- characterize delisting support across the intended research universe; or
- authorize Phase 2 feature research on an incomplete Phase 1 foundation.

Those remain separate acceptance gates.
