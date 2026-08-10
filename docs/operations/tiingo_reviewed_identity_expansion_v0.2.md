# Tiingo reviewed identity expansion v0.2

> **Superseded for current operator use.** The first live private-workspace run of the v0.4
> expansion failed closed on `ALGN` and `AMP`. Do not promote v0.4 from this procedure. Use
> `docs/operations/tiingo_reviewed_identity_reconciliation_v0.1.md`, which preserves the Align
> provider-coverage defect and models Ameriprise when-issued history explicitly in v0.5.

## Purpose

This increment widened the reviewed Tiingo engineering slice from seven to thirteen permanent
instrument identities while preserving the fail-closed identity, session-completeness, canonical
price, and feature pipeline. It is retained as the historical record of the v0.4 review proposal.

It does not promote the other durable campaign symbols by ticker assumption. The six proposed series
were selected because their public trading starts are inside the configured 1996+ acquisition window
and could be pinned to primary issuer/SEC evidence without ticker-derived identity.

## Added reviewed series

| Query symbol | Reviewed start | Exchange | Evidence basis |
| --- | --- | --- | --- |
| `A` | 1999-11-18 | XNYS | Agilent SEC material identifies November 18, 1999 as the first trading day; SEC filings identify NYSE common stock. |
| `AKAM` | 1999-10-29 | XNAS | Akamai Form 10-K states public trading commenced October 29, 1999 under `AKAM` on Nasdaq. |
| `ALGN` | 2001-01-26 | XNAS | Align Form 10-K states public trading commenced January 26, 2001 under `ALGN` on Nasdaq. |
| `AMZN` | 1997-05-15 | XNAS | Amazon investor relations states the company went public May 15, 1997; SEC filings identify `AMZN` on Nasdaq. |
| `AIZ` | 2004-02-05 | XNYS | Assurant Form 10-K states trading began February 5, 2004 on NYSE under `AIZ`. |
| `AMP` | 2005-10-03 | XNYS | SEC-filed Ameriprise release states October 3, 2005 was its first trading day as an independent public company on NYSE under `AMP`. |

The previous seven reviewed identities remain unchanged. The proposed combined snapshot was
`tiingo-reviewed-identity-candidate-v0.4` with thirteen instruments and seventeen dated symbol-history
intervals.

## Historical v0.4 gate sequence

The v0.4 procedure below is retained for traceability only and must not be used for current promotion.
Its live run exposed the discrepancies that caused v0.5 reconciliation.

```powershell
uv run python .\scripts\expand_tiingo_reviewed_identity.py --root "$HOME\trade-scout-private"
```

The command read only the existing private durable profile and made no provider calls. In the live
workspace it correctly rejected the proposed thirteen-name classification set rather than weakening
the review rules.

The v0.4 identity-to-canonical mapping remains reserved as
`tiingo-reviewed-identity-candidate-v0.4` -> `tiingo-reviewed-split-only-v0.3` so corrected content is
not silently assigned to a previously published version identity.

## Failure semantics

A provider history that begins after a sourced first trading date is not silently accepted as a full
history. The expansion or expected-session gate exposes the discrepancy. No missing bar is fabricated
or interpolated. A provider transport failure is likewise not reclassified as a market-data gap.

## Scope boundary

This remains a bounded engineering validation slice, not a historical S&P 500 research universe.
Provider acceptance is unchanged, serving selection is unchanged, and the current S&P snapshot is not
used as evidence of historical constituent membership. The remaining durable symbols require their own
reviewed identity/lineage evidence before canonical promotion.
