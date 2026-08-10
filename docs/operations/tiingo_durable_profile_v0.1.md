# Tiingo durable profile v0.1

## Purpose

`profile-tiingo` inspects the checksum-verified Tiingo history already stored in the private operator
workspace. It makes **no Tiingo API calls** and does not require `TIINGO_API_TOKEN`.

The profiler re-verifies every durable receipt before reading its raw payload. The output contains
only derived diagnostics, dates, counts, and receipt/checksum provenance identifiers; raw OHLCV or
adjusted price values are not copied into the report.

## Run

From the SCOUT repository root:

```powershell
uv run python .\scripts\trade_scout_workspace.py profile-tiingo --root "$HOME\trade-scout-private"
```

The report is written to:

```text
<workspace>/evidence/tiingo-profile/profile.json
```

## Diagnostics

For each acquired source symbol the report records:

- row count and first/last observed date;
- invalid, duplicate, or non-monotonic dates;
- rows missing the established Tiingo daily field contract;
- invalid/non-finite numeric rows;
- raw OHLC ordering violations;
- negative volume observations;
- non-1 split-factor event count;
- non-zero cash-dividend event count; and
- calendar gaps longer than seven days.

A long calendar gap is only a **screening observation**. It is not classified as a missing market
session because the profiler does not silently invent an exchange calendar, listing interval, halt,
or corporate-action explanation.

## Fail-closed behavior

Profiling is blocked if the operator workspace is receipt/state inconsistent. Each receipt is
checksum-verified again before its payload is parsed. Multiple full-history receipts for the same
source symbol are rejected rather than double-counted or silently selected.

The report is research/data-quality evidence only. It does not promote Tiingo to accepted primary
provider status, create canonical bars, fill missing sessions, alter provider data, or perform
feature/pattern/ranking logic.
