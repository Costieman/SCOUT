# Tiingo durable profile report v0.1

## Purpose

The profile report turns the derived evidence produced by `profile-tiingo` into a local HTML view
without exposing licensed Tiingo rows. It makes no provider calls and displays no raw OHLCV or
adjusted-price values.

The report summarizes:

- profiled symbol and row counts;
- structural anomaly symbol count;
- invalid, duplicate, and non-monotonic date counts;
- missing required fields and invalid numeric rows;
- OHLC ordering and negative-volume violations;
- observed split and dividend event counts;
- long calendar-gap screening observations;
- the 15 shortest observed histories; and
- a table of all profiled symbols with coverage and event counts.

## Run

From the SCOUT repository root:

```powershell
uv run python .\scripts\render_tiingo_profile_report.py --root "$HOME\trade-scout-private" --open-browser
```

The HTML report is written to:

```text
<workspace>/evidence/tiingo-profile/report.html
```

The input remains:

```text
<workspace>/evidence/tiingo-profile/profile.json
```

The renderer cross-checks aggregate symbol, row, split, and dividend counts against the per-symbol
entries and fails closed when the derived profile is inconsistent. This is presentation of research
and data-quality evidence only; it does not create canonical bars, infer listing history, promote
Tiingo to accepted-provider status, or perform strategy research.
