# Stooq inactive/delisted coverage evidence

This workflow characterizes whether Stooq returns historical daily OHLCV for securities that an independent source identifies as inactive or delisted.

It is evidence-only. A missing Stooq series is recorded as `NO_HISTORY`; it is not interpreted as proof of delisting or as evidence about the reason for absence. A present series is compared with an independently supplied terminal trading date when one is available.

Run multiple independently reviewed cases, for example:

```powershell
uv run python scripts/run_stooq_inactive_evidence.py `
  --case "OLD1.US,reviewed-old1,2010-01-01,2020-12-31,2020-06-30" `
  --case "OLD2.US,reviewed-old2,2012-01-01,2021-12-31,2021-03-15"
```

Use `NONE` as the terminal-date field only when an independent reference establishes inactivity but does not provide a sufficiently precise final trading date. Such a case remains `INCONCLUSIVE` for terminal-date fidelity.

Exact Stooq CSV responses are preserved under `runtime/stooq-inactive-evidence/raw/` and remain outside Git. The report is written under `runtime/stooq-inactive-evidence/report/`.

A successful report characterizes only the supplied query symbols. It does not demonstrate a complete historical delisted universe, terminal returns, bankruptcy outcomes, symbol continuity, or provider acceptance. The free-edition research scope must remain explicit if coverage is incomplete.
