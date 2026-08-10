# Tiingo split-only normalization preview v0.1

## Purpose

This preview exercises real, checksum-verified private Tiingo EOD rows against the promoted reviewed
instrument master without promoting any price rows. It derives Trade Scout's split-only price basis
from raw OHLC plus Tiingo `splitFactor`, keeps `divCash` separate, and routes the resulting provider
bars through the identity-aware canonical normalizer.

The output is diagnostics/provenance only. It never writes raw OHLCV values, Tiingo `adj*` prices,
or canonical daily bars.

## Split semantics

Tiingo documents a split's EOD `splitFactor` on the split ex-date as `splitTo / splitFrom`; the split
ex-date is also the date used for split adjustments. Trade Scout's provider contract instead expects
a cumulative split-only **price multiplier**.

For a row on date `d`, the preview therefore computes:

```text
price_multiplier(d) = 1 / product(splitFactor(e) for split ex-dates e > d)
split_adjusted_OHLC(d) = raw_OHLC(d) * price_multiplier(d)
```

The event on date `d` is deliberately excluded from the multiplier for that same row because the raw
price on the ex-date is already on the post-split share basis. Forward splits therefore reduce older
prices; reverse splits increase older prices. Dividends never enter the split-only multiplier.

Tiingo's published `adjOpen`, `adjHigh`, `adjLow`, and `adjClose` incorporate both split and dividend
adjustments, so they are not used as Trade Scout canonical split-only prices. For any reviewed series
with zero observed `divCash` events, the preview uses those vendor adjusted fields only as a
cross-check of the split-only transformation. A mismatch fails the preview validation but still does
not promote price rows.

Official semantics references retained in the generated preview:

- `https://www.tiingo.com/documentation/corporate-actions/splits`
- `https://www.tiingo.com/documentation/end-of-day`

## Preconditions

The command requires:

1. a consistent private workspace and durable Tiingo receipts;
2. the reviewed identity candidate at
   `evidence/instrument-identity/tiingo-reviewed-candidate.json`;
3. the matching immutable promoted instrument-master snapshot in `canonical-store`.

The candidate and immutable snapshot must match exactly. Only the candidate's explicitly reviewed
Tiingo provider-series links are included; the rest of the acquired campaign remains out of scope.

## Run

From the SCOUT repository root:

```powershell
uv run python .\scripts\preview_tiingo_split_only.py --root "$HOME\trade-scout-private"
```

The metadata-only report is written to:

```text
<workspace>/evidence/split-normalization/tiingo-reviewed-preview.json
```

The terminal summary reports row/event counts, cross-check eligibility/mismatches, canonical
normalization issues, validation state, and `price_rows_promoted: 0`.

## Validation meaning

`validation_passed=true` requires all reviewed rows to normalize through the promoted permanent
identities and dated symbol history with no normalization issues, no canonical quality issues, and no
vendor-adjusted mismatch on series eligible for the no-dividend cross-check.

This is a normalization preview, not dataset promotion and not Tiingo provider acceptance. It does
not prove exchange-session completeness, historical-universe correctness, corporate-action
completeness, or suitability of the remaining campaign symbols.
