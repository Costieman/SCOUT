# Trade Scout Edge Explorer v0.1

## Purpose

Edge Explorer is a research-only application surface for asking a deliberately narrow question:
for one reviewed stock and one explicit strategy definition, what did comparable historical events
look like, and where in a nearby parameter region does any apparent continuation advantage occur?

It is not a scanner, recommendation engine, strategy optimizer, or production signal. The research
program explicitly seeks stable parameter regions rather than isolated optima, and requires later
cross-stock, comparator, out-of-sample, robustness, cost, and risk work before promotion.

## Initial strategy

Version 0.1 exposes the first Trade Scout research family only:

- `consolidation_breakout`
- prior-window duration is configurable;
- consolidation qualifies when `(highest high - lowest low) / lowest low` is at or below the
  configured maximum range;
- the breakout boundary is the highest high in the prior qualified window;
- the signal is a daily close above that boundary (the B2 family in the first research program);
- optional trend context is none, price above the 200-session SMA, or price above a rising
  200-session SMA;
- a five-session exploratory cooldown suppresses immediate repeated signals;
- execution is next-session open;
- outcome horizons are 5, 10, 20, 40, and 60 sessions.

The cooldown/reset policy is intentionally provisional and versioned. It must be replaced by the
full pattern-instance/event-family semantics before confirmatory research.

## What the screen shows

For the selected stock/configuration, the application displays:

1. event count and forward-return distribution at the selected horizon;
2. mean, median, probability of positive return, P25/P75, median MFE and median MAE across fixed
   horizons;
3. a simple same-stock trend-context baseline sampled every five sessions;
4. mean-return difference between the breakout sample and that simple baseline;
5. the latest observable setup state (`NOT_QUALIFIED`, `TREND_FILTER_FAIL`, `TRIGGER_READY`, or
   `BREAKOUT`);
6. a duration × tightness surface showing where apparent excess mean return is positive/negative;
7. recent event dates and complete definition/dataset provenance.

## Interpretation boundary

`EXPLORATORY_POSITIVE` means only that, in this one stock and selected historical slice, the mean
return exceeded the simple baseline and at least half of complete outcomes were positive with at
least ten observations. It does **not** mean the strategy is validated or production-eligible.

The parameter surface is especially vulnerable to data mining. An isolated attractive cell is weak
evidence. Broad nearby regions are more interesting, but still require the formal research program:
trend baseline, duration, tightness, breakout-definition comparison, volume/regime work, risk,
then frozen unseen-data and walk-forward validation.

The current comparator is not market-, sector-, or regime-matched and overlapping observations are
not statistically independent. These limitations are displayed in the UI.

## Data boundary

The application does not call Tiingo, Alpha Vantage, Stooq, Alpaca, or any other provider. It reads
an explicitly selected immutable canonical dataset and resolves symbols through the reviewed
identity candidate. Split-adjusted canonical OHLC is required; non-PASS rows and unresolved
identity/history are blocked.

For this first single-stock research preview, canonical rows are treated as in-scope for the selected
instrument rather than reconstructing the complete point-in-time broad-universe eligibility filter.
That means the preview is useful for within-stock hypothesis generation, not for estimating the
full research-program universe effect.

## Running locally

From the repository environment, with an existing private operator workspace that has a selected
canonical dataset and reviewed identity candidate:

```bash
uv run python scripts/serve_edge_explorer.py --root <PRIVATE_WORKSPACE_ROOT> --open-browser
```

The browser opens `/research/edge`. The normal application console also links to Edge Explorer when
the edge source is configured.

## Next increments

- register research previews as immutable experiment records rather than ad-hoc query runs;
- replace provisional cooldown with full PatternState/EventRecord identity and reset semantics;
- add trend-only baseline as an explicit selectable experiment/strategy family;
- add broader cross-stock cohort surfaces rather than relying on one instrument;
- add matched comparator and uncertainty intervals;
- add 120/252-session outcomes where dataset history permits;
- add MAE/MFE and drawdown visual distributions, then simple risk-policy experiments;
- retain null/negative results and parameter surfaces rather than optimizing them away.
