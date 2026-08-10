# Tiingo reviewed identity expansion v0.2

## Purpose

This increment widens the reviewed Tiingo engineering slice from seven to thirteen permanent
instrument identities while preserving the fail-closed identity, session-completeness, canonical
price, and feature pipeline.

It does not promote the other durable campaign symbols by ticker assumption. The six added series
were selected because their public trading starts are inside the configured 1996+ acquisition window
and can be pinned to primary issuer/SEC evidence without requiring unresolved predecessor-symbol
history.

## Added reviewed series

| Query symbol | Reviewed start | Exchange | Evidence basis |
| --- | --- | --- | --- |
| `A` | 1999-11-18 | XNYS | Agilent SEC material identifies November 18, 1999 as the first trading day; SEC filings identify NYSE common stock. |
| `AKAM` | 1999-10-29 | XNAS | Akamai Form 10-K states public trading commenced October 29, 1999 under `AKAM` on Nasdaq. |
| `ALGN` | 2001-01-26 | XNAS | Align Form 10-K states public trading commenced January 26, 2001 under `ALGN` on Nasdaq. |
| `AMZN` | 1997-05-15 | XNAS | Amazon investor relations states the company went public May 15, 1997; SEC filings identify `AMZN` on Nasdaq. |
| `AIZ` | 2004-02-05 | XNYS | Assurant Form 10-K states trading began February 5, 2004 on NYSE under `AIZ`. |
| `AMP` | 2005-10-03 | XNYS | SEC-filed Ameriprise release states October 3, 2005 was its first trading day as an independent public company on NYSE under `AMP`. |

The previous seven reviewed identities remain unchanged. The combined snapshot is
`tiingo-reviewed-identity-candidate-v0.4` with thirteen instruments and seventeen dated symbol-history
intervals.

## Local gate sequence

From the repository root, after pulling the merged change:

```powershell
uv run python .\scripts\expand_tiingo_reviewed_identity.py --root "$HOME\trade-scout-private"
```

The command reads only the existing private durable profile. It makes no provider calls and requires
all thirteen reviewed query series to be present with the expected lineage-start classifications.

If that passes, promote the immutable instrument master using the exact v0.4 seed file:

```powershell
uv run python .\scripts\trade_scout_workspace.py promote-tiingo-identity --root "$HOME\trade-scout-private" --config configs/tiingo_reviewed_identity_seeds_v0.4.json
```

Then run the canonical price promotion:

```powershell
uv run python .\scripts\promote_tiingo_reviewed_prices.py --root "$HOME\trade-scout-private"
```

For a v0.4 identity candidate the operator script explicitly targets the new immutable canonical
version `tiingo-reviewed-split-only-v0.3`; prior v0.1 and v0.2 canonical datasets are not mutated.
The canonical promotion still re-verifies durable receipts, rebuilds split-only prices, requires
strict PASS normalization/quality, and requires complete expected XNYS/XNAS sessions before writing.

After promotion, audit the new dataset explicitly:

```powershell
uv run python .\scripts\audit_canonical_session_completeness.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.3
```

Then build the existing five-feature set over the new immutable canonical version:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.3
```

## Failure semantics

A provider history that begins after a sourced first trading date is not silently accepted as a full
history. The expansion or expected-session gate exposes the discrepancy. No missing bar is fabricated
or interpolated. A provider transport failure is likewise not reclassified as a market-data gap.

## Scope boundary

This remains a bounded engineering validation slice, not a historical S&P 500 research universe.
Provider acceptance is unchanged, serving selection is unchanged, and the current S&P snapshot is not
used as evidence of historical constituent membership. The remaining durable symbols require their own
reviewed identity/lineage evidence before canonical promotion.
