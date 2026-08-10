# Tiingo symbol-lineage audit v0.1

## Purpose

The lineage audit compares the first date observed in the derived local Tiingo profile with a small,
explicit set of externally sourced ticker-lineage cases. It exists to test an architectural risk:
provider history addressed by a current ticker can begin before that ticker itself became effective.

The audit is offline after the source cases are checked in. It makes no Tiingo calls and reads no raw
OHLCV values; it consumes only `<workspace>/evidence/tiingo-profile/profile.json`.

## Seed cases

`configs/tiingo_symbol_lineage_cases_v0.1.json` currently contains three bounded cases:

- APTV, including the DLPH to APTV transition;
- AXON, including TASR to AAXN and AAXN to AXON; and
- ALLE, including the when-issued and regular-way transition.

Each event has an effective date and an explicit source URL. These cases are research probes, not a
complete symbol master and not proof of Tiingo's behavior for other instruments.

## Run

From the SCOUT repository root, after `profile-tiingo` has generated the local profile:

```powershell
uv run python .\scripts\audit_tiingo_symbol_lineage.py --root "$HOME\trade-scout-private"
```

The output is written to:

```text
<workspace>/evidence/tiingo-lineage/audit.json
```

## Classifications

The audit may report:

- `NOT_PROFILED`;
- `WHEN_ISSUED_START_MATCH`;
- `PRE_CURRENT_SYMBOL_HISTORY_OBSERVED`;
- `PRE_REGULAR_WAY_HISTORY_OBSERVED`;
- `CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH`; or
- `CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED`.

A pre-current-symbol observation is not automatically a data error. It is evidence that provider
retrieval and canonical instrument identity cannot be modeled as the same thing. Trade Scout must
retain dated symbol lineage and permanent internal identities rather than silently treating ticker as
identity.

The audit does not rewrite provider rows, infer missing lineage, create canonical bars, or change the
Tiingo acceptance decision.
