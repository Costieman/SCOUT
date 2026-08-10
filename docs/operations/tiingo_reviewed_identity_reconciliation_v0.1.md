# Tiingo reviewed identity reconciliation v0.1

## Purpose

This increment reconciles the first live private-workspace run of reviewed identity candidate v0.4.
The v0.4 gate correctly failed closed because two newly reviewed series did not match the expected
provider-history classifications: `ALGN` began later than the sourced public-trading start, while
`AMP` contained history before regular-way trading.

The failed v0.4 review is not rewritten in place. The reconciled snapshot is a new immutable identity
candidate, `tiingo-reviewed-identity-candidate-v0.5`.

## Align: defer rather than fit the vendor

Align Technology SEC filings state that public trading commenced on January 26, 2001 under `ALGN` on
Nasdaq. The durable Tiingo profile begins on January 30, 2001. The sourced date remains authoritative
for the reviewed lifecycle; Trade Scout does not move the identity start forward merely to make the
provider look complete.

`ALGN` is therefore excluded from the v0.5 promotion batch and remains an explicit provider-coverage
follow-up. Missing expected sessions must be independently resolved or adjudicated before this series
can enter a canonical reviewed slice. No bars are fabricated or interpolated.

Primary evidence:

- https://www.sec.gov/Archives/edgar/data/1097149/000109714902000007/align_10k.htm

## Ameriprise: preserve the when-issued phase

Ameriprise separation materials establish that a when-issued market existed before the distribution
and that regular-way trading began after distribution. The durable Tiingo profile first observes the
series on September 15, 2005; an SEC-filed company release identifies October 3, 2005 as the first
trading day as an independent public company on the NYSE under `AMP`.

The exact September 15 first-observed date comes from the checksum-verified private Tiingo profile,
not from the SEC filing. The public evidence establishes the meaning of the pre-October-3 phase.
Accordingly, v0.5 records two explicit dated symbol-history intervals for the same permanent identity:

- `AMP WI`: 2005-09-15 through 2005-10-02
- `AMP`: 2005-10-03 onward

Primary evidence:

- https://www.sec.gov/Archives/edgar/data/820027/000104746905021562/a2158640zex-99_1.htm
- https://www.sec.gov/Archives/edgar/data/52428/000090342305000749/exhibit-99.htm

## Reconciled scope

The v0.5 candidate contains twelve instruments and seventeen dated symbol-history intervals. It keeps
the previous seven reviewed identities and adds `A`, `AKAM`, `AMZN`, `AIZ`, and `AMP`. `ALGN` is
explicitly deferred rather than silently accepted with incomplete provider coverage.

The operator maps v0.5 to a new immutable canonical dataset version,
`tiingo-reviewed-split-only-v0.4`. The earlier v0.4 identity-to-v0.3 canonical mapping is retained as
published history rather than reused for corrected content.

## Local gate sequence

After pulling the merged change, build the reconciled candidate:

```powershell
uv run python .\scripts\expand_tiingo_reviewed_identity.py --root "$HOME\trade-scout-private"
```

Expected structural result: twelve instruments, seventeen dated symbol-history intervals, zero
coverage gaps, and `promotion_ready: true`. The output also lists `ALGN` as deferred.

Promote only the exact reconciled identity seed set:

```powershell
uv run python .\scripts\trade_scout_workspace.py promote-tiingo-identity --root "$HOME\trade-scout-private" --config configs/tiingo_reviewed_identity_seeds_v0.5.json
```

Then promote canonical prices through the existing quality and expected-session gates:

```powershell
uv run python .\scripts\promote_tiingo_reviewed_prices.py --root "$HOME\trade-scout-private"
```

Audit the new immutable canonical version explicitly:

```powershell
uv run python .\scripts\audit_canonical_session_completeness.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.4
```

Build the existing feature set over that exact version only after canonical promotion and session
completeness pass:

```powershell
uv run python .\scripts\build_initial_feature_slice.py --root "$HOME\trade-scout-private" --dataset-version tiingo-reviewed-split-only-v0.4
```

## Scope boundary

This is still a bounded engineering validation slice, not a historical S&P 500 research universe.
Tiingo provider acceptance is unchanged, serving selection is unchanged, and no pattern-engine
readiness is implied. The other durable campaign symbols still require reviewed identity and lineage
evidence before canonical promotion.
