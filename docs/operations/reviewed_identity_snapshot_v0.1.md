# Reviewed identity snapshot candidate v0.1

## Purpose

The reviewed identity candidate turns explicit identity-review seeds plus the private Tiingo lineage
audit into permanent Trade Scout instrument IDs and dated canonical symbol history. It does not
promote price rows and it does not treat a current ticker as permanent identity.

The first seed set is deliberately narrow: APTV, AXON, and ALLE. It exists to exercise the identity
model against the continuity behavior already observed in the local Tiingo profile.

## Identity rules

- Permanent `instrument_id` values are derived from opaque review IDs such as `rir-000002`, not from
  ticker, company name, exchange, or a current Tiingo query symbol.
- The Tiingo query symbol is retained separately from a stable reviewed provider-series ID such as
  `tiingo-series:rir-000002`.
- Dated canonical symbol history is created only for intervals that have explicit reviewed evidence.
- The constructor never backfills an unknown predecessor start date from Tiingo's first observed row.
- If the provider history begins before the earliest reviewed symbol interval, that interval is
  recorded as a coverage gap and candidate promotion remains blocked.

This distinction is important for continuity series. A provider request using current symbol `AXON`
may contain rows from periods when the reviewed canonical symbol was `AAXN` or `TASR`. Provider query
symbology and canonical historical symbol identity are separate concepts.

## Current bounded seed coverage

The checked-in configuration is:

```text
configs/tiingo_reviewed_identity_seeds_v0.1.json
```

It contains only symbol intervals supported by the lineage sources already captured in the audit:

- APTV from 2017-12-05 onward;
- AAXN from 2017-04-06 through 2021-01-25, then AXON from 2021-01-26 onward; and
- ALLE when-issued from 2013-11-18 through 2013-12-01, then regular-way ALLE from 2013-12-02 onward.

The constructor is expected to leave the observed APTV pre-2017 and AXON pre-2017 spans unresolved
until independent evidence establishes their earlier dated symbol assignments. Those gaps are not
filled from provider continuity behavior alone.

## Operator command

After `profile-tiingo` and the Tiingo lineage audit have been generated:

```powershell
uv run python .\scripts\trade_scout_workspace.py build-tiingo-identity --root "$HOME\trade-scout-private"
```

The metadata-only candidate is written to:

```text
<workspace>/evidence/instrument-identity/tiingo-reviewed-candidate.json
```

The command re-verifies durable receipts before building the candidate. It makes no Tiingo API calls
and does not include raw OHLCV values.

## Promotion semantics

`promotion_ready` is true only when every audited observed-history span for every seed has reviewed
dated symbol coverage. The initial three-case candidate is expected to remain blocked because APTV
and AXON have unresolved predecessor-history start spans.

A blocked candidate is still useful: its permanent IDs, reviewed intervals, provider-series links,
and explicit coverage gaps can be consumed by later normalization and review tooling. It is not a
complete instrument master and must not be presented as one.
