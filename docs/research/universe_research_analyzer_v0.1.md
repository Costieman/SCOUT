# Universe Research Analyzer v0.1

## Purpose

The Universe Research Analyzer is the first market-wide exploratory research surface in Trade Scout.
It applies one explicit strategy definition independently to every instrument in a supplied research
universe and then aggregates event frequency, cross-sectional breadth, forward outcomes and nearby
parameter behavior.

It is designed to answer questions such as:

- how many qualifying setups occurred across the available market scope;
- how many different stocks contributed those setups;
- how many setups appeared per month;
- what the forward return, MFE and MAE distributions looked like;
- whether the result differs from a simple same-stock trend-context baseline; and
- whether an apparent effect persists across nearby consolidation durations and tightness values.

## Current universe boundary

Version 0.1 deliberately exposes only `reviewed_canonical`.

This means the analyzer uses every fully reviewed Tiingo-linked instrument that is present in the
selected immutable canonical dataset and has no unresolved reviewed identity/history gap. It does
**not** infer historical S&P 500 membership from today's constituents and it must not label the
result as an S&P 500-wide historical result.

A future point-in-time S&P 500 membership source can implement the same application source contract
without changing the statistics or presentation layers.

## Baseline strategy family

The first supported strategy remains `consolidation_breakout`:

1. inspect a prior fixed-duration window;
2. require its high-low range to be below a configured threshold;
3. optionally require a point-in-time moving-average trend condition;
4. require the signal close to finish above the prior-window highest high;
5. optionally require signal-day volume to exceed a multiple of the prior 20-session average; and
6. measure outcomes from the next session open.

Supported trend conditions include:

- no moving-average filter;
- close above SMA 200;
- close above a rising SMA 200;
- close above SMA 50, SMA 100 and SMA 200; and
- bullish stack: close > SMA 50 > SMA 100 > SMA 200.

Breakout volume can be disabled or required to exceed 1.0x, 1.25x, 1.5x or 2.0x the prior
20-session average from the UI.

## Research window and outcomes

The user selects a trailing research window of 1, 2, 3, 5, 10 or 20 years relative to the latest
session available in the selected canonical universe.

The initial UI supports 2, 3, 5, 10, 20, 40 and 60-session outcome horizons. Signal detection may use
history before the requested research window for warm-up and moving-average calculation, but only
signals inside the requested window are counted. Outcomes that would exit after the analysis end
are not included as complete observations.

## Market-wide evidence

For the selected configuration the report exposes:

- universe instrument count;
- total historical setup count;
- instruments with at least one setup and breadth fraction;
- mean, median, maximum and active-month setup frequency;
- selected-horizon sample size, mean, median, positive fraction, P25 and P75;
- median MFE and MAE;
- a simple same-instrument trend-context comparator and excess mean return;
- top-five event concentration;
- monthly setup counts and contributing-stock counts; and
- per-stock contribution summaries.

These are descriptive exploratory statistics. Version 0.1 does not claim inferential validation.

## Parameter surface

The initial parameter surface varies consolidation duration and maximum base range while holding the
selected trend filter, breakout-volume gate and outcome horizon fixed. Each cell reports:

- event count;
- number of contributing instruments;
- number of complete outcomes;
- mean forward return;
- positive-return fraction;
- mean return relative to the same-stock trend-context comparator; and
- mean setup frequency per month.

The surface is intended to show whether an effect occupies a broad region rather than to select the
single best cell. Parameter maxima remain exposed to multiple-testing and data-mining risk.

## Explicit non-goals for v0.1

This slice does not yet implement:

- historical point-in-time S&P 500 membership;
- daily/2-day/3-day/weekly resampling as separate pattern timeframes;
- ATR or volatility stop policies;
- transaction costs or slippage;
- walk-forward or held-out validation;
- multiple-testing correction;
- experiment-registry promotion;
- current-market scanning or alerts; or
- broker or order-execution integration.

Those are downstream layers. In particular, stop-policy research should be applied to an already
fixed event population so that stop selection does not redefine which historical breakouts existed.

## Operator entry point

```text
uv run python scripts/serve_research_workbench.py --root <PRIVATE_WORKSPACE_ROOT> --open-browser
```

The launcher requires a selected canonical dataset and reviewed identity candidate in the private
operator workspace. The application makes no provider calls while running research.
