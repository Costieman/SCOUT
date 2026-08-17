# Readable Edge Foundation v0.1

## Purpose

The Market-Wide Strategy Lab already measures a useful exploratory event population. The next step is not to add more descriptive tables or silently change the strategy definition. It is to make the economic and statistical meaning of the existing run readable.

This slice therefore sits on top of the current market-wide research engine. It reconstructs the selected strategy outcomes and current simple comparator and fails if their sample counts or means do not reproduce the existing `UniverseResearchReport`.

The formal research state remains `EXPLORATORY`.

## What this slice adds

`trade_scout.statistics.readable_edge` adds a report layer containing:

- mean, median, standard deviation, win rate, average win/loss, payoff ratio, expectancy and profit factor;
- return tails, skewness, excess kurtosis and winner concentration;
- a 95% calendar-month cluster-bootstrap interval for the raw mean;
- a 95% Wilson score interval for win probability;
- the existing same-instrument trend-context comparator with a paired calendar-month bootstrap interval for the mean excess;
- a deterministic randomized eligible-timing control that preserves each instrument's selected-event count, uses the same horizon, samples only trend-qualified eligible dates and records its seed;
- parameter-surface diagnostics that expose how many alternatives were searched, how many beat the current comparator, the selected cell's local neighbour stability and the best observed cell;
- mechanical 0/5/10/25/50/100 bps round-trip friction sensitivity and a raw break-even friction estimate; and
- a plain-language preliminary verdict while leaving OOS, multiple-testing and portfolio gates visibly incomplete.

## Preliminary verdicts

The readable layer may emit:

- `INSUFFICIENT_SAMPLE`
- `NO_EDGE_VS_SIMPLE_BASELINE`
- `NOT_DISTINGUISHABLE_FROM_RANDOM_TIMING`
- `RAW_EDGE_UNCERTAIN`
- `PARAMETER_REGION_UNSTABLE`
- `PRELIMINARY_EDGE`

These labels are diagnostic summaries, not research-governance promotion states. Even `PRELIMINARY_EDGE` remains `EXPLORATORY` until the governed validation stack supplies the required evidence.

## Statistical interpretation

The month-cluster bootstrap is a first dependence-aware uncertainty estimate for the exploratory report. It clusters observations by signal calendar month so that events sharing a broad market period are resampled together. It is intentionally simple and reproducible; it does not replace later block-bootstrap, HAC, walk-forward, PBO/CSCV or data-snooping procedures.

The randomized timing comparator is a negative/control-style timing test. For each instrument it samples, without replacement, the same number of complete control observations as that instrument contributed complete strategy events. Candidate dates must satisfy the configured point-in-time trend condition and the same data-quality/horizon rules. The output includes the null mean distribution, 95% null range, excess versus the null mean and a one-sided empirical p-value.

The current simple comparator is retained for continuity. It is not re-labelled as a matched independent benchmark.

## Cost boundary

The friction table subtracts a fixed round-trip basis-point assumption from each event's mean return. It answers only how much mechanical friction the raw event mean can absorb. It does not model spreads by instrument, market impact, liquidity, portfolio overlap, position sizing or capital constraints.

## Operator entry point

After this slice is merged:

```powershell
uv run python scripts/run_readable_edge.py `
  --root "<WORKSPACE_ROOT>" `
  --pattern-timeframe daily `
  --lookback-years 2 `
  --horizon 20 `
  --duration 20 `
  --max-range-pct 12 `
  --trend-filter above_sma_50_100_200 `
  --volume-ratio none `
  --open-browser
```

The command reads only the selected immutable canonical dataset and the reviewed identity candidate. It makes no market-data provider calls. It writes checksummed JSON and a printable HTML report under:

```text
<WORKSPACE_ROOT>/evidence/readable-edge/
```

## Deliberately deferred

This slice does not claim to complete the full research specification. Still required are:

- matched broad-market and sector benchmarks;
- formal stop/target selection and R-multiple research on untouched validation data;
- full research-family multiple-testing/data-snooping correction;
- walk-forward and final-holdout evidence;
- point-in-time stock/sector/regime attribution;
- realistic spread/slippage/liquidity modelling; and
- portfolio sizing, overlap, concentration, cash and drawdown simulation.

The intended order remains: reproduce the current report first, make the edge readable second, then add increasingly strict validation without changing the underlying event population silently.
