# Tiingo / Alpha Vantage complementarity campaign v0.1

## Purpose

This campaign answers a narrow data-foundation question: when Tiingo and Alpha Vantage are queried
for the same reviewed U.S.-equity session window, how much expected-session coverage is unique to
each source, how much is corroborated, and how often the overlapping raw OHLCV values disagree?

The objective is to measure complementarity before deciding whether one-sided provider observations
should ever be eligible for a provenance-preserving canonical composite after explicit review.

## Scope

The first campaign uses eight deliberately ordinary, liquid U.S. equities across Nasdaq and NYSE.
The fixed window is 2026-04-01 through 2026-08-07 so Alpha Vantage can remain on its compact daily
endpoint. The cases are processed in small operator-selected batches to limit quota and rate-limit
risk.

The campaign compares each provider against the pinned
`us-equities-core-full-day-v0.1` expected-session calendar. For every case it records derived counts
for:

- sessions observed by both providers with raw OHLCV agreement;
- sessions observed by both providers with one or more raw OHLCV disagreements;
- Tiingo-only sessions;
- Alpha-Vantage-only sessions;
- expected sessions observed by neither provider;
- coverage of Tiingo alone, Alpha Vantage alone, and the union of both;
- the incremental expected-session coverage contributed by each provider to the union.

No raw OHLCV values are written to the report or uploaded as Actions artifacts.

## Safety boundary

This is an evidence campaign, not canonical reconciliation. In every run:

- `canonical_fill_allowed=false`;
- `canonical_dataset_written=false`;
- `price_rows_promoted=0`;
- `bars_fabricated=0`;
- provider acceptance does not change;
- serving selection does not change;
- disagreements are reported, never averaged;
- one-sided observations remain review candidates, not automatic gap fills.

The workflow uses `TIINGO_API_TOKEN` and `ALPHA_VANTAGE_API_KEY` only through GitHub Actions
Secrets. Credentials are not written to the repository, report, logs, or artifacts.

## GitHub Actions operation

Open **Actions -> Tiingo Alpha complementarity campaign -> Run workflow**.

The workflow accepts two inputs:

- `offset`: zero-based index of the first configured case;
- `max_cases`: maximum number of cases to run before stopping.

The default is three cases per invocation. The eight-case campaign can therefore be covered with
three bounded runs, for example offsets `0`, `3`, and `6` with `max_cases=3`.

Each run uploads only:

```text
runtime/tiingo-alpha-complementarity/report.json
```

under a run-specific Actions artifact. If either provider fails, the current batch stops and the
partial derived report is still uploaded.

## Interpretation

A positive `union_gain_over_tiingo_fraction` means Alpha Vantage supplied expected sessions Tiingo
did not observe in the same window. A positive `union_gain_over_alpha_vantage_fraction` means the
reverse. These are coverage measurements only; they do not establish which observation is correct.

`BOTH_DISAGREE` is equally important. A pair of feeds can appear complete while disagreeing on the
actual OHLCV values. Any future composite promotion must therefore retain the existing explicit
adjudication and row-provenance gates rather than treating union coverage as sufficient evidence.

A short recent-window campaign cannot characterize deep-history availability, delisted-security
coverage, or provider correction behavior. Historical gaps such as the reviewed ALGN 2001 case
remain separate targeted validation problems.

## Decision gate

After all batches complete, review the aggregate union gains and disagreement burden. Only if the
evidence shows material complementary coverage with a manageable review burden should Trade Scout
expand this into a larger or older-window campaign. If the union adds little coverage, the project
should not increase complexity merely because two provider feeds are available.
